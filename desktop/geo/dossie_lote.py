# -*- coding: utf-8 -*-
"""OpenRotas Desktop — LOTE DE DOSSIÊS DE ROTA (§11 — processamento em lote).

Lê uma planilha (.xlsx/.csv) com pares ORIGEM/DESTINO (nomes de cidade "Cidade/UF" ou coordenadas
"lon,lat") e gera um Excel CONSOLIDADO: uma linha por par com o resumo da integração de dados
(UFs atravessadas, trechos de rio, navegáveis, pontes, travessias, hidrovias, portos, cruzamentos
ferroviários, nº de alertas). Reutiliza o Dossiê de Rota. Puro/defensivo: nunca levanta; linhas com
erro saem marcadas, sem abortar o lote.

Colunas de entrada aceitas (sem distinção de acento/caixa): origem|origin|de|o / destino|destination|
para|d. Puro stdlib + pandas/openpyxl (já dependências)."""
from __future__ import annotations

import sys
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.lote")

_COL_ORIGEM = ("origem", "origin", "de", "o", "partida")
_COL_DESTINO = ("destino", "destination", "para", "d", "chegada")


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()


def ler_pares(caminho) -> list:
    """Lê a planilha e devolve [(origem, destino), ...]. Detecta as colunas por nome. [] em falha."""
    try:
        import pandas as pd
        p = Path(caminho)
        if p.suffix.lower() in (".csv", ".txt"):
            df = pd.read_csv(p)
        else:
            df = pd.read_excel(p)
        cols = {_norm(c): c for c in df.columns}
        co = next((cols[k] for k in cols if k in _COL_ORIGEM), None)
        cd = next((cols[k] for k in cols if k in _COL_DESTINO), None)
        if co is None or cd is None:
            # fallback: usa as 2 primeiras colunas
            if len(df.columns) >= 2:
                co, cd = df.columns[0], df.columns[1]
            else:
                return []
        pares = []
        for _, row in df.iterrows():
            o, d = str(row[co]).strip(), str(row[cd]).strip()
            if o and d and o.lower() != "nan" and d.lower() != "nan":
                pares.append((o, d))
        return pares
    except Exception:
        logger.warning("[LOTE] falha ao ler %s.", caminho, exc_info=True)
        return []


def _coords_de(texto):
    """'lon,lat' → (lon,lat) se parecer coordenada; senão None (trata como nome)."""
    t = str(texto).strip()
    if t.count(",") == 1:
        try:
            a, b = t.split(",")
            return (float(a), float(b))
        except Exception:
            return None
    return None


def _resumo_linha(origem, destino, dd) -> dict:
    cam = dd.get("camadas", {})
    h = dd.get("hidrografia", {})
    tt = dd.get("travessia_territorial", {})
    o = dd.get("origem", {}).get("municipio", {})
    d = dd.get("destino", {}).get("municipio", {})
    return {
        "origem": origem, "destino": destino,
        "origem_municipio": "%s/%s" % (o.get("nome", "?"), o.get("uf", "?")),
        "destino_municipio": "%s/%s" % (d.get("nome", "?"), d.get("uf", "?")),
        "ufs_corredor": ", ".join(tt.get("ufs", [])),
        "municipios_corredor": tt.get("n_municipios", 0),
        "trechos_rio": h.get("trechos", 0),
        "rios_navegaveis": h.get("navegaveis", 0),
        "pontes": cam.get("pontes", {}).get("feicoes", 0),
        "travessias": cam.get("travessias", {}).get("feicoes", 0),
        "hidrovias": cam.get("hidrovias", {}).get("feicoes", 0),
        "portos": cam.get("complexos_portuarios", {}).get("feicoes", 0),
        "ferrovias": cam.get("ferrovias", {}).get("feicoes", 0),
        "rota_real_osrm": bool(dd.get("rota_real")),
        "alertas": len(dd.get("alertas", [])),
    }


def processar_lote(caminho_in, caminho_out=None, folga_km: float = 3.0, usar_osrm: bool = False) -> dict:
    """Processa todos os pares e grava o Excel consolidado. {ok, linhas, erros, saida}. Não levanta."""
    from geo import dossie_rota as dr
    pares = ler_pares(caminho_in)
    if not pares:
        return {"ok": False, "linhas": 0, "erros": 0, "saida": None, "detalhe": "planilha sem pares válidos"}
    linhas, erros = [], 0
    for origem, destino in pares:
        try:
            co, cd = _coords_de(origem), _coords_de(destino)
            if co and cd:
                dd = dr.dossie([co, cd], folga_km=folga_km, usar_osrm=usar_osrm)
            else:
                dd, _ = dr.dossie_por_nomes([origem, destino], folga_km=folga_km, usar_osrm=usar_osrm)
            if dd.get("erro"):
                erros += 1
                linhas.append({"origem": origem, "destino": destino, "erro": dd["erro"]})
            else:
                linhas.append(_resumo_linha(origem, destino, dd))
        except Exception:
            erros += 1
            linhas.append({"origem": origem, "destino": destino, "erro": "falha no processamento"})
    try:
        import pandas as pd
        if caminho_out is None:
            caminho_out = Path(caminho_in).with_name("dossies_lote.xlsx")
        caminho_out = Path(caminho_out)
        caminho_out.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(caminho_out), engine="openpyxl") as xw:
            pd.DataFrame(linhas).to_excel(xw, sheet_name="Rotas", index=False)
        return {"ok": True, "linhas": len(linhas), "erros": erros, "saida": str(caminho_out)}
    except Exception:
        logger.warning("[LOTE] falha ao gravar o Excel consolidado.", exc_info=True)
        return {"ok": False, "linhas": len(linhas), "erros": erros, "saida": None, "detalhe": "erro ao gravar"}


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    entrada = next((a for a in argv if a.lower().endswith((".xlsx", ".csv", ".txt"))), None)
    if not entrada:
        print("uso: --dossie-lote entrada.xlsx [saida.xlsx] [--osrm]")
        return 2
    saidas = [a for a in argv if a.lower().endswith(".xlsx") and a != entrada]
    saida = saidas[0] if saidas else None
    r = processar_lote(entrada, saida, usar_osrm=("--osrm" in argv))
    if r["ok"]:
        print("Lote processado: %d rota(s) (%d com erro). Consolidado: %s" % (r["linhas"], r["erros"], r["saida"]))
        return 0
    print("Falha no lote: %s" % r.get("detalhe", "?"))
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
