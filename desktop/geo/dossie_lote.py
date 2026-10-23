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
    cir = dd.get("circuidade") or {}        # distância/sinuosidade (quando o sensor rodou)
    dl = dd.get("dor_logistica") or {}      # índice executivo de dificuldade (0-100)
    return {
        "origem": origem, "destino": destino,
        "origem_municipio": "%s/%s" % (o.get("nome", "?"), o.get("uf", "?")),
        "destino_municipio": "%s/%s" % (d.get("nome", "?"), d.get("uf", "?")),
        "ufs_corredor": ", ".join(tt.get("ufs", [])),
        "municipios_corredor": tt.get("n_municipios", 0),
        # Distância e sinuosidade (rodoviária real quando o OSRM local está no ar; senão estimativa).
        "reta_km": cir.get("reta_km"),
        "viaria_km": cir.get("viaria_km"),
        "circuidade_fator": cir.get("fator"),
        "circuidade_nivel": cir.get("nivel", ""),
        "fonte_distancia": cir.get("fonte", ""),
        # Dor logística (0-100) e nível — leitura de dificuldade do destino.
        "dor_logistica": dl.get("indice"),
        "dor_nivel": dl.get("nivel", ""),
        "acesso_fluvial": bool(dl.get("fluvial")),
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


def _agregar_lote(linhas) -> dict:
    """Agrega as linhas de resultado (sem as de erro) num retrato executivo do lote. PURO.
    {total, ok, erros, n_balsa, n_fluvial, n_dor_alta, dist_media, dist_max, dor_media, dor_max,
     pior_destino, pior_dor, uf_top, uf_top_n}."""
    def _num(v):
        try:
            f = float(v)
            return f if f == f else None   # descarta NaN
        except (TypeError, ValueError):
            return None
    ok = [l for l in (linhas or []) if not l.get("erro")]
    erros = sum(1 for l in (linhas or []) if l.get("erro"))
    dists = [x for x in (_num(l.get("viaria_km")) for l in ok) if x is not None]
    dores = [x for x in (_num(l.get("dor_logistica")) for l in ok) if x is not None]
    n_balsa = sum(1 for l in ok if _num(l.get("travessias")) and _num(l.get("travessias")) > 0)
    n_fluvial = sum(1 for l in ok if l.get("acesso_fluvial"))
    n_dor_alta = sum(1 for l in ok if str(l.get("dor_nivel", "")).upper() == "ALTA")
    pior_destino, pior_dor = "", None
    for l in ok:
        dv = _num(l.get("dor_logistica"))
        if dv is not None and (pior_dor is None or dv > pior_dor):
            pior_dor, pior_destino = dv, str(l.get("destino_municipio") or l.get("destino") or "")
    _uf_cont = {}
    for l in ok:
        for uf in str(l.get("ufs_corredor", "") or "").split(","):
            uf = uf.strip()
            if uf:
                _uf_cont[uf] = _uf_cont.get(uf, 0) + 1
    uf_top, uf_top_n = ("", 0)
    if _uf_cont:
        uf_top, uf_top_n = max(_uf_cont.items(), key=lambda kv: kv[1])
    _media = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {
        "total": len(linhas or []), "ok": len(ok), "erros": erros,
        "n_balsa": n_balsa, "n_fluvial": n_fluvial, "n_dor_alta": n_dor_alta,
        "dist_media": _media(dists), "dist_max": (round(max(dists), 1) if dists else None),
        "dor_media": _media(dores), "dor_max": (round(max(dores), 1) if dores else None),
        "pior_destino": pior_destino, "pior_dor": pior_dor,
        "uf_top": uf_top, "uf_top_n": uf_top_n,
    }


def _narrativa_lote(agg) -> str:
    """Narrativa executiva (texto) a partir dos agregados do lote. PURO — recebe o dict de _agregar_lote.
    Espelha a leitura do analista do web (_narrativa_executiva_lote), aqui offline e por par de dossiê."""
    def _i(k):
        try:
            return int(agg.get(k) or 0)
        except (TypeError, ValueError):
            return 0
    total = _i("total")
    if total <= 0:
        return "Nenhuma rota válida para resumir."
    partes = ["Foram processadas %d rota(s)" % total]
    erros = _i("erros")
    if erros:
        partes[-1] += " (%d com erro de processamento)" % erros
    partes[-1] += "."
    nb, nf = _i("n_balsa"), _i("n_fluvial")
    if nb or nf:
        h = []
        if nb:
            h.append("**%d** no corredor de travessia/balsa" % nb)
        if nf:
            h.append("**%d** com acesso fluvial/isolado (IBGE REGIC)" % nf)
        partes.append("Do total, " + " e ".join(h) + " — pontos que exigem atenção logística especial.")
    else:
        partes.append("Nenhuma rota depende de balsa nem tem acesso fluvial/isolado — malha integralmente rodoviária.")
    dm, dx = agg.get("dist_media"), agg.get("dist_max")
    if dm is not None:
        partes.append("Distância viária média de **%.0f km**%s."
                      % (dm, (" (máxima %.0f km)" % dx) if dx is not None else ""))
    dmed = agg.get("dor_media")
    nda = _i("n_dor_alta")
    pior = str(agg.get("pior_destino") or "").strip()
    pdor = agg.get("pior_dor")
    _d = []
    if dmed is not None:
        _d.append("dor logística média de **%.0f/100**" % dmed)
    if nda:
        _d.append("**%d** destino(s) de dor ALTA" % nda)
    if _d:
        partes.append("Dificuldade: " + " e ".join(_d) + ".")
    if pior and pdor is not None:
        partes.append("O destino mais difícil é **%s** (%.0f/100)." % (pior, pdor))
    uf = str(agg.get("uf_top") or "").strip()
    if uf and _i("uf_top_n") > 0:
        partes.append("Em cobertura, a UF **%s** aparece em mais corredores (%d)." % (uf, _i("uf_top_n")))
    return " ".join(partes)


def processar_lote(caminho_in, caminho_out=None, folga_km: float = 3.0, usar_osrm=None,
                   progresso=None) -> dict:
    """Processa todos os pares e grava o Excel consolidado. {ok, linhas, erros, saida}. Não levanta.
    `progresso` (opcional): callback chamado por par com {feito, total, origem, destino} — a UI usa
    para a barra de progresso do lote. `usar_osrm` segue o padrão das demais ferramentas: None=AUTO
    (usa o OSRM local se estiver no ar → distância rodoviária real; senão estima), True força, False
    nunca usa. Assim o lote também aproveita o motor local auto-iniciado, sem o usuário mexer em nada."""
    from geo import dossie_rota as dr
    pares = ler_pares(caminho_in)
    if not pares:
        return {"ok": False, "linhas": 0, "erros": 0, "saida": None, "detalhe": "planilha sem pares válidos"}
    linhas, erros = [], 0
    total = len(pares)
    for _i, (origem, destino) in enumerate(pares, 1):
        if progresso is not None:
            try:
                progresso({"feito": _i, "total": total, "origem": origem, "destino": destino})
            except Exception:
                pass
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
        agg = _agregar_lote(linhas)
        with pd.ExcelWriter(str(caminho_out), engine="openpyxl") as xw:
            # Aba 1: RESUMO EXECUTIVO (agregado + narrativa) — leitura rápida antes do detalhe.
            _rotulos = [
                ("Rotas processadas", agg["total"]), ("Com sucesso", agg["ok"]), ("Com erro", agg["erros"]),
                ("No corredor de balsa/travessia", agg["n_balsa"]),
                ("Acesso fluvial/isolado (REGIC)", agg["n_fluvial"]),
                ("Destinos de dor ALTA", agg["n_dor_alta"]),
                ("Distância viária média (km)", agg["dist_media"]),
                ("Distância viária máxima (km)", agg["dist_max"]),
                ("Dor logística média (0-100)", agg["dor_media"]),
                ("Dor logística máxima (0-100)", agg["dor_max"]),
                ("Destino mais difícil", agg["pior_destino"]),
                ("UF em mais corredores", ("%s (%d)" % (agg["uf_top"], agg["uf_top_n"])) if agg["uf_top"] else ""),
            ]
            pd.DataFrame(_rotulos, columns=["Indicador", "Valor"]).to_excel(
                xw, sheet_name="Resumo Executivo", index=False)
            pd.DataFrame({"Leitura executiva": [_narrativa_lote(agg)]}).to_excel(
                xw, sheet_name="Resumo Executivo", index=False, startrow=len(_rotulos) + 2)
            # Aba 2: detalhe por rota.
            pd.DataFrame(linhas).to_excel(xw, sheet_name="Rotas", index=False)
        return {"ok": True, "linhas": len(linhas), "erros": erros, "saida": str(caminho_out),
                "resumo": agg}
    except Exception:
        logger.warning("[LOTE] falha ao gravar o Excel consolidado.", exc_info=True)
        return {"ok": False, "linhas": len(linhas), "erros": erros, "saida": None, "detalhe": "erro ao gravar"}


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    entrada = next((a for a in argv if a.lower().endswith((".xlsx", ".csv", ".txt"))), None)
    if not entrada:
        print("uso: --dossie-lote entrada.xlsx [saida.xlsx] [--osrm | --geodesico]")
        return 2
    saidas = [a for a in argv if a.lower().endswith(".xlsx") and a != entrada]
    saida = saidas[0] if saidas else None
    # AUTO por padrão (usa o OSRM local se no ar); --osrm força; --geodesico/--sem-osrm desliga.
    if "--osrm" in argv:
        usar = True
    elif ("--geodesico" in argv) or ("--sem-osrm" in argv):
        usar = False
    else:
        usar = None
    r = processar_lote(entrada, saida, usar_osrm=usar)
    if r["ok"]:
        print("Lote processado: %d rota(s) (%d com erro). Consolidado: %s" % (r["linhas"], r["erros"], r["saida"]))
        return 0
    print("Falha no lote: %s" % r.get("detalhe", "?"))
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
