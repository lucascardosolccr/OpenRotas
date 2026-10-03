# -*- coding: utf-8 -*-
"""OpenRotas Desktop — BENCHMARK de motores de rota (§9/§29).

Mede, com EVIDÊNCIA (não suposição), o desempenho de um endpoint OSRM em pares O/D reais do
Brasil: latência (média/mediana/p95), vazão (rotas/s) e taxa de sucesso. Serve para comparar
objetivamente, como o plano pede:

    OSRM PÚBLICO (nuvem)   ×   OSRM LOCAL (desktop)

Uso:
    python benchmark.py --url http://localhost:5000 --rotulo "OSRM local"
    python benchmark.py --url http://router.project-osrm.org --rotulo "OSRM público"
    python benchmark.py            # compara os dois de uma vez (padrão)

Somente stdlib (sem dependências novas). Respeita o motor público (poucas chamadas, 1 por vez)."""
from __future__ import annotations

import os
import csv
import sys
import time
import json
import argparse
import statistics
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(AQUI, "sample_pairs.csv")


def carregar_pares(caminho: str):
    pares = []
    try:
        with open(caminho, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pares.append((row["origem"], float(row["lon_o"]), float(row["lat_o"]),
                              float(row["lon_d"]), float(row["lat_d"])))
    except Exception as e:
        print("Não consegui ler %s: %s" % (caminho, e))
    return pares


def _uma_rota(url: str, lon_o, lat_o, lon_d, lat_d, timeout=15.0):
    alvo = ("%s/route/v1/driving/%s,%s;%s,%s?overview=false&alternatives=3"
            % (url.rstrip("/"), lon_o, lat_o, lon_d, lat_d))
    t0 = time.time()
    try:
        with urllib.request.urlopen(alvo, timeout=timeout) as r:
            dados = json.loads(r.read())
        dt = time.time() - t0
        if dados.get("code") == "Ok" and dados.get("routes"):
            km = min(x.get("distance", float("inf")) for x in dados["routes"]) / 1000.0
            return dt, round(km, 1)
    except Exception:
        pass
    return (time.time() - t0), None


def medir(url: str, rotulo: str, pares, pausa_s: float = 0.0):
    print("\n== %s (%s) ==" % (rotulo, url))
    lat_ok, sucessos, total = [], 0, len(pares)
    for nome, lon_o, lat_o, lon_d, lat_d in pares:
        dt, km = _uma_rota(url, lon_o, lat_o, lon_d, lat_d)
        ok = km is not None
        sucessos += 1 if ok else 0
        if ok:
            lat_ok.append(dt)
        print("  %-26s %6.2fs  %s" % (nome[:26], dt, ("%s km" % km) if ok else "FALHOU"))
        if pausa_s:
            time.sleep(pausa_s)
    res = {"rotulo": rotulo, "url": url, "total": total, "sucessos": sucessos,
           "taxa_sucesso_pct": round(100.0 * sucessos / total, 1) if total else 0.0}
    if lat_ok:
        lat_ok.sort()
        res.update({
            "lat_media_s": round(statistics.mean(lat_ok), 2),
            "lat_mediana_s": round(statistics.median(lat_ok), 2),
            "lat_p95_s": round(lat_ok[max(0, int(len(lat_ok) * 0.95) - 1)], 2),
            "vazao_rota_s": round(len(lat_ok) / sum(lat_ok), 2) if sum(lat_ok) else 0.0,
        })
    return res


def _tabela(resultados):
    cols = ["rotulo", "taxa_sucesso_pct", "lat_media_s", "lat_mediana_s", "lat_p95_s", "vazao_rota_s"]
    cab = {"rotulo": "Motor", "taxa_sucesso_pct": "Sucesso%", "lat_media_s": "Média(s)",
           "lat_mediana_s": "Mediana(s)", "lat_p95_s": "p95(s)", "vazao_rota_s": "Rotas/s"}
    print("\n" + "=" * 72)
    print("  ".join("%-12s" % cab[c] for c in cols))
    print("-" * 72)
    for r in resultados:
        print("  ".join("%-12s" % str(r.get(c, "-")) for c in cols))
    print("=" * 72)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Benchmark de motor OSRM (OpenRotas Desktop)")
    ap.add_argument("--url", help="URL de um OSRM específico para medir (senão compara local × público)")
    ap.add_argument("--rotulo", default="OSRM")
    ap.add_argument("--amostra", default=SAMPLE, help="CSV de pares O/D")
    ap.add_argument("--pausa", type=float, default=0.0, help="segundos entre chamadas (use >1 no público)")
    args = ap.parse_args(argv)

    pares = carregar_pares(args.amostra)
    if not pares:
        print("Sem pares para medir."); return 2

    resultados = []
    if args.url:
        resultados.append(medir(args.url, args.rotulo, pares, args.pausa))
    else:
        # Padrão: compara local × público (respeitando o público com pausa de 1,2 s).
        resultados.append(medir("http://localhost:5000", "OSRM local", pares, 0.0))
        resultados.append(medir("http://router.project-osrm.org", "OSRM público", pares, 1.2))
    _tabela(resultados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
