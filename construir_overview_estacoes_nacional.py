# -*- coding: utf-8 -*-
"""
construir_overview_estacoes_nacional.py
=======================================
Gera o OVERVIEW NACIONAL de ESTAÇÕES FLUVIOMÉTRICAS da ANA/SNIRH — um asset leve, versionado no
repositório, com estações REAIS (código ANA de 8 dígitos) espalhadas por TODO o Brasil. Assim a
sub-aba "Cotas & Vazões" consulta cotas/vazões de estações reais em qualquer região do país SEM
depender do catálogo completo (snirh_estacaos.csv, ~91 MB, baixado sob demanda).

Cobertura garantida por AMOSTRAGEM ESPACIAL: o território é dividido numa grade; em cada célula
ficam as estações fluviométricas prioritárias (operando + telemétricas primeiro). Só estações
brasileiras, tipoEstacao=1 (fluviométrica → mede nível/vazão).

Entrada:  snirh_estacaos.csv (catálogo ANA/SNIRH completo — baixe pelo botão do app ou pelo Release
          lucascardosolccr/openrotas-dados). Caminho por argv[1] ou ./snirh_estacaos.csv.
Saída:    data/estacoes_nacional_overview.csv.gz  (~0,1 MB, versionado no git)

Uso:  python construir_overview_estacoes_nacional.py [caminho_snirh_estacaos.csv]
"""
import os
import sys

import pandas as pd

OUT = os.path.join("data", "brasil", "ibge", "derivadas", "estacoes_nacional_overview.csv.gz")
CELL_DEG, POR_CELULA = 0.6, 3

_UF = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPÁ": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARÁ": "CE",
    "DISTRITO FEDERAL": "DF", "ESPÍRITO SANTO": "ES", "GOIÁS": "GO", "MARANHÃO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG", "PARANÁ": "PR",
    "PARAÍBA": "PB", "PARÁ": "PA", "PERNAMBUCO": "PE", "PIAUÍ": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDÔNIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SÃO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO",
}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "snirh_estacaos.csv"
    # idFormatadoComZero é o CÓDIGO ANA de 8 dígitos, com zeros à esquerda → ler como STRING.
    df = pd.read_csv(src, low_memory=False, dtype={"idFormatadoComZero": str})
    df = df[df["nomeEstado"].isin(_UF)].copy()
    df = df[pd.to_numeric(df["tipoEstacao"], errors="coerce") == 1]     # fluviométrica (cota/vazão)
    df = df.dropna(subset=["latitude", "longitude", "idFormatadoComZero"])
    df["codigo"] = df["idFormatadoComZero"].astype(str).str.strip()
    df = df[df["codigo"].str.fullmatch(r"\d{6,10}")]                    # códigos plausíveis
    df["uf"] = df["nomeEstado"].map(_UF)
    df["tipo"] = df["tipoEstacaoTelemetrica"].apply(
        lambda v: "Telemétrica" if str(v).strip() in ("1", "1.0") else "Convencional")
    df["nome"] = df["nome"].astype(str).str.strip()
    df["rio"] = df.get("nomeRio", "").astype(str).str.strip()
    df["bacia"] = df.get("codigoNomeBacia", df.get("baciaCodigo", "")).astype(str).str.strip()
    df["op"] = pd.to_numeric(df["operando"], errors="coerce").fillna(0)
    df["tel"] = pd.to_numeric(df["tipoEstacaoTelemetrica"], errors="coerce").fillna(0)

    # amostragem espacial: prioriza operando + telemétrica; top-N por célula → cobre o país todo
    df["cx"] = (df["longitude"] / CELL_DEG).round()
    df["cy"] = (df["latitude"] / CELL_DEG).round()
    df = df.sort_values(["op", "tel"], ascending=False)
    sel = df.groupby(["cx", "cy"], sort=False).head(POR_CELULA)

    out = (sel[["codigo", "nome", "rio", "bacia", "uf", "latitude", "longitude", "tipo"]]
           .rename(columns={"latitude": "lat", "longitude": "lon"})
           .sort_values(["uf", "nome"]).reset_index(drop=True))
    out["lat"] = out["lat"].round(5)
    out["lon"] = out["lon"].round(5)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.to_csv(OUT, index=False, compression="gzip")
    print("OK: %d estações (27 UFs esperadas: %d) · telemétricas=%d → %s (%.2f MB gz)"
          % (len(out), out["uf"].nunique(), (out["tipo"] == "Telemétrica").sum(),
             OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
