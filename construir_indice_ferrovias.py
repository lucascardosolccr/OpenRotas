# -*- coding: utf-8 -*-
"""
construir_indice_ferrovias.py
=============================
Gera o ÍNDICE NACIONAL DE FERROVIAS — asset leve, versionado no repositório, que permite descobrir
LOCALMENTE (sem rede) a ferrovia mais próxima de um ponto, com a operadora/linha, a bitola e a situação.
Enriquece o contexto de infraestrutura das rotas.

Como a base tem poucos trechos (~889), amostra pontos AO LONGO da geometria (a cada ~2 km) para ter boa
densidade espacial — em vez de só o ponto representativo de cada trecho.

Entrada:  data/brasil/ibge/derivadas/ferrovias.parquet (IBGE BC250; já versionada, ~1,6 MB)
Saída:    data/brasil/ibge/derivadas/ferrovias_index.parquet  (~pequeno, versionado no git)

Uso:  python construir_indice_ferrovias.py
"""
import math
import os
import struct

import pandas as pd

DER = os.path.join("data", "brasil", "ibge", "derivadas")
OUT = os.path.join(DER, "ferrovias_index.parquet")
PASSO_KM = 2.0     # amostra ~1 ponto a cada 2 km ao longo do trecho


def _linha_wkb(w):
    """WKB LINESTRING → lista de (lon, lat). [] p/ outros tipos ou nulo."""
    if not w:
        return []
    try:
        endian = "<" if w[0] == 1 else ">"
        t = struct.unpack_from(endian + "I", w, 1)[0]
        if t != 2:
            return []
        n = struct.unpack_from(endian + "I", w, 5)[0]
        pts = struct.unpack_from(endian + "d" * (2 * n), w, 9)
        return [(pts[i], pts[i + 1]) for i in range(0, 2 * n, 2)]
    except Exception:
        return []


def _amostra(linha, passo_km):
    """Amostra pontos ao longo da polilinha a cada ~passo_km (sempre inclui extremos)."""
    if len(linha) < 2:
        return linha
    out = [linha[0]]
    acc = 0.0
    for (x1, y1), (x2, y2) in zip(linha, linha[1:]):
        d = math.hypot((x2 - x1) * math.cos(math.radians((y1 + y2) / 2)), (y2 - y1)) * 111.32
        acc += d
        if acc >= passo_km:
            out.append((x2, y2))
            acc = 0.0
    if out[-1] != linha[-1]:
        out.append(linha[-1])
    return out


def main():
    df = pd.read_parquet(os.path.join(DER, "ferrovias.parquet"),
                         columns=["geometry_wkb", "nome", "bitola", "situacaofi"])
    linhas = []
    for _, r in df.iterrows():
        via = str(r.get("nome") or "").strip()
        if not via:
            continue
        bit = str(r.get("bitola") or "").strip()
        sit = str(r.get("situacaofi") or "").strip()
        for (lon, lat) in _amostra(_linha_wkb(r.get("geometry_wkb")), PASSO_KM):
            linhas.append((round(lat, 5), round(lon, 5), via, bit, sit))
    out = pd.DataFrame(linhas, columns=["lat", "lon", "via", "bitola", "situacao"])
    out = out.drop_duplicates(subset=["lat", "lon", "via"]).reset_index(drop=True)
    for c in ("via", "bitola", "situacao"):
        out[c] = out[c].astype("category")
    out.to_parquet(OUT, compression="gzip", index=False)
    print("OK: %d pontos · %d ferrovias/operadoras → %s (%.2f MB)"
          % (len(out), out["via"].nunique(), OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
