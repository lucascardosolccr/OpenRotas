# -*- coding: utf-8 -*-
"""
construir_indice_rios_nomeados.py
=================================
Gera o ÍNDICE NACIONAL de RIOS NOMEADOS — asset leve, versionado no repositório, que permite descobrir
LOCALMENTE (sem rede e sem o Parquet pesado de 451 MB) o nome do rio mais próximo de um ponto. Isso torna a
"estação ANA de referência" da rota mais EXATA: com o nome do rio, o app casa a estação no MESMO rio e
classifica a referência como "direta".

Como fica leve e útil: mantém só os rios SIGNIFICATIVOS (≥ 20 trechos na drenagem BC250) MAIS todos os rios
que têm estação na rede ANA nacional (para o casamento estação↔rio funcionar), e reduz a ~1 ponto por célula
de ~1 km por rio. Descarta córregos/igarapés minúsculos que só poluiriam o vizinho-mais-próximo.

Entrada:  data/brasil/ibge/derivadas/drenagem.parquet (BC250; camada pesada, baixada sob demanda)
          + data/brasil/ibge/derivadas/estacoes_nacional_overview.csv.gz (rede ANA — para preservar seus rios)
Saída:    data/brasil/ibge/derivadas/rios_nomeados_index.parquet  (~5 MB, versionado no git)

Uso:  python construir_indice_rios_nomeados.py
"""
import os
import unicodedata

import pandas as pd

DER = os.path.join("data", "brasil", "ibge", "derivadas")
OUT = os.path.join(DER, "rios_nomeados_index.parquet")
MIN_TRECHOS = 20          # rios com pelo menos este nº de trechos entram (os demais só se tiverem estação ANA)
CELULA_DEC = 2            # 2 casas decimais ≈ célula de ~1 km para o afinamento

_PREFIXOS = ("RIO ", "IGARAPE ", "CORREGO ", "RIBEIRAO ", "RIACHO ", "ARROIO ", "LAGO ",
             "LAGOA ", "CANAL ", "REPRESA ", "ACUDE ", "BRACO ", "PARANA ")


def _norm(s):
    t = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").upper().strip()
    for p in _PREFIXOS:
        if t.startswith(p):
            t = t[len(p):]
            break
    return " ".join(t.split())


def main():
    df = pd.read_parquet(os.path.join(DER, "drenagem.parquet"), columns=["nome", "lon", "lat"])
    nm = df["nome"].astype(str).str.strip()
    df = df[(nm != "") & (~nm.str.lower().isin(["nan", "none"]))].copy()
    df["nome"] = nm[df.index]
    df = df.dropna(subset=["lat", "lon"])

    cont = df["nome"].value_counts()
    keep = set(cont[cont >= MIN_TRECHOS].index)
    try:
        est = pd.read_csv(os.path.join(DER, "estacoes_nacional_overview.csv.gz"))
        rios_est = set(est["rio"].dropna().map(_norm))
        keep |= {n for n in df["nome"].unique() if _norm(n) in rios_est}
    except Exception:
        pass

    sub = df[df["nome"].isin(keep)].copy()
    sub["gy"] = sub["lat"].round(CELULA_DEC)
    sub["gx"] = sub["lon"].round(CELULA_DEC)
    thin = sub.drop_duplicates(subset=["gy", "gx", "nome"])[["lat", "lon", "nome"]].copy()
    thin["lat"] = thin["lat"].round(5)
    thin["lon"] = thin["lon"].round(5)
    thin["nome"] = thin["nome"].astype("category")
    thin = thin.reset_index(drop=True)
    thin.to_parquet(OUT, compression="gzip", index=False)
    print("OK: %d pontos · %d rios nomeados → %s (%.2f MB)"
          % (len(thin), thin["nome"].nunique(), OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
