# -*- coding: utf-8 -*-
"""
construir_indice_rodovias.py
============================
Gera o ÍNDICE NACIONAL DE RODOVIAS SIGNIFICATIVAS — asset leve, versionado no repositório, que permite
descobrir LOCALMENTE (sem rede e sem o Parquet pesado de 122 MB) a rodovia mais próxima de um ponto, com a
sua sigla (BR-101…), jurisdição (Federal/Estadual) e revestimento. Serve para enriquecer o contexto
rodoviário das rotas (origem/destino) sem depender do download da camada pesada.

Significativas = trechos com SIGLA (BR-/XX-) ou de jurisdição Federal/Estadual — descarta vicinais/leito
natural sem identificação, que só poluiriam o vizinho-mais-próximo. Afina a ~1 ponto por célula de ~1 km.

Entrada:  data/brasil/ibge/derivadas/rodovias.parquet (IBGE BC250; camada pesada, baixada sob demanda)
Saída:    data/brasil/ibge/derivadas/rodovias_index.parquet  (~1 MB, versionado no git)

Uso:  python construir_indice_rodovias.py
"""
import os

import pandas as pd

DER = os.path.join("data", "brasil", "ibge", "derivadas")
OUT = os.path.join(DER, "rodovias_index.parquet")
CELULA_DEC = 2


def main():
    df = pd.read_parquet(os.path.join(DER, "rodovias.parquet"),
                         columns=["sigla", "nome", "jurisdicao", "revestimen", "lon", "lat"])
    sig = df["sigla"].astype(str).str.strip().replace({"nan": "", "None": ""})
    jur = df["jurisdicao"].astype(str)
    signif = (sig != "") | jur.str.contains("Federal", case=False, na=False) | jur.str.contains("Estadual", case=False, na=False)
    df = df[signif].dropna(subset=["lat", "lon"]).copy()
    df["sigla"] = sig[df.index]
    df["nome"] = df["nome"].astype(str).str.strip().replace({"nan": "", "None": ""})
    df["via"] = df["sigla"].where(df["sigla"] != "", df["nome"])       # sigla (BR-101) ou, na falta, o nome
    df = df[df["via"] != ""]
    df["jur"] = jur[df.index].str.replace("Estadual/Distrital", "Estadual", regex=False)
    df["rev"] = df["revestimen"].astype(str).replace({"nan": "—", "None": "—"})

    df["gy"] = df["lat"].round(CELULA_DEC)
    df["gx"] = df["lon"].round(CELULA_DEC)
    thin = df.drop_duplicates(subset=["gy", "gx", "via"])[["lat", "lon", "via", "jur", "rev"]].copy()
    thin["lat"] = thin["lat"].round(5)
    thin["lon"] = thin["lon"].round(5)
    for c in ("via", "jur", "rev"):
        thin[c] = thin[c].astype("category")
    thin = thin.reset_index(drop=True)
    thin.to_parquet(OUT, compression="gzip", index=False)
    print("OK: %d pontos · %d rodovias → %s (%.2f MB)"
          % (len(thin), thin["via"].nunique(), OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
