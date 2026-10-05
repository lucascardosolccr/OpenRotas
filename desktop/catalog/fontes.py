# -*- coding: utf-8 -*-
"""OpenRotas Desktop — CATÁLOGO DE FONTES E DADOS (§14/§15/§33/§69/§70).

Responde, para cada base instalada, "de onde veio este dado?" (§70) com RASTREABILIDADE completa:
organização, dataset, versão, licença, portal, finalidade — metadados DECLARADOS — cruzados com
FATOS MEDIDOS do arquivo real (instalado?, bytes, nº de registros, hash, procedência embarcada nas
colunas fonte_base/fonte_versao). Nada é inventado (§71): a procedência (BC250/BC100 e as versões
2016–2025) é lida dos próprios dados; o que é declarado (nome da organização, portal, licença) está
marcado como metadado declarado.

Distingue fonte PRIMÁRIA (órgão responsável), COMPLEMENTAR e AUXILIAR (§69). Gera o Catálogo de
Dados Nacionais em texto e Markdown (§15). Puro/defensivo: nunca levanta."""
from __future__ import annotations

import sys
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.catalog")

# Metadados DECLARADOS por recurso (o que não vive dentro do arquivo): organização responsável,
# tipo de fonte (§69), licença, portal e finalidade. A procedência fina (BC250/BC100 + versões)
# é LIDA do dado. IBGE BC = Base Cartográfica Contínua (dados abertos); ANA/SNIRH p/ hidrometria.
FONTE_META = {
    "municipios": {"org": "IBGE", "tipo": "primaria", "licenca": "Dados abertos (IBGE)",
                   "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                   "finalidade": "Limites e sedes municipais; geocodificação nacional"},
    "massas_dagua": {"org": "IBGE", "tipo": "primaria", "licenca": "Dados abertos (IBGE)",
                     "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                     "finalidade": "Lagos/represas/corpos d'água — inteligência hidrográfica"},
    "drenagem": {"org": "IBGE", "tipo": "primaria", "licenca": "Dados abertos (IBGE)",
                 "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                 "finalidade": "Rede de drenagem/rios nacional — detecção fluvial"},
    "rodovias": {"org": "IBGE", "tipo": "primaria", "licenca": "Dados abertos (IBGE)",
                 "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                 "finalidade": "Malha rodoviária nacional — contexto/decisão rodoviária"},
    "hidrografia_nacional": {"org": "IBGE/ANA", "tipo": "primaria", "licenca": "Dados abertos",
                             "portal": "https://www.ibge.gov.br/geociencias",
                             "finalidade": "Índice/grafo hidrográfico nacional"},
    "ferrovias": {"org": "IBGE", "tipo": "primaria", "licenca": "Dados abertos (IBGE)",
                  "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                  "finalidade": "Malha ferroviária nacional"},
    "pontes": {"org": "IBGE", "tipo": "primaria", "licenca": "Dados abertos (IBGE)",
               "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
               "finalidade": "Pontes (transposição rodoviária sobre água)"},
    "travessias": {"org": "IBGE", "tipo": "primaria", "licenca": "Dados abertos (IBGE)",
                   "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                   "finalidade": "Travessias/balsas"},
    "hidrovias": {"org": "IBGE/ANTAQ", "tipo": "primaria", "licenca": "Dados abertos",
                  "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                  "finalidade": "Rede aquaviária/hidrovias"},
    "eclusas": {"org": "IBGE", "tipo": "primaria", "licenca": "Dados abertos (IBGE)",
                "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                "finalidade": "Eclusas (transposição de desnível)"},
    "atracadouros_terminal": {"org": "IBGE/ANTAQ", "tipo": "primaria", "licenca": "Dados abertos",
                              "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                              "finalidade": "Atracadouros/terminais aquaviários"},
    "complexos_portuarios": {"org": "IBGE/ANTAQ", "tipo": "primaria", "licenca": "Dados abertos",
                             "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                             "finalidade": "Complexos portuários"},
    "sinalizacao": {"org": "IBGE/Marinha", "tipo": "auxiliar", "licenca": "Dados abertos",
                    "portal": "https://www.ibge.gov.br/geociencias/cartografia-e-mapas",
                    "finalidade": "Sinalização náutica"},
    "rios_nomeados": {"org": "ANA/IBGE", "tipo": "complementar", "licenca": "Dados abertos",
                      "portal": "https://metadados.snirh.gov.br/",
                      "finalidade": "Índice de rios nomeados (estação ANA mais próxima)"},
    "amazonia_fluvial": {"org": "IBGE/ANA", "tipo": "complementar", "licenca": "Dados abertos",
                         "portal": "https://metadados.snirh.gov.br/",
                         "finalidade": "Grafo fluvial amazônico"},
    "snirh_rios": {"org": "ANA/SNIRH", "tipo": "complementar", "licenca": "Dados abertos (ANA)",
                   "portal": "https://www.snirh.gov.br/hidroweb/",
                   "finalidade": "Rios SNIRH (hidrometria/telemetria de referência)"},
    "osrm_brasil": {"org": "OpenStreetMap (via OSRM)", "tipo": "primaria", "licenca": "ODbL (OSM)",
                    "portal": "https://www.openstreetmap.org/",
                    "finalidade": "Grafo de roteamento rodoviário local/offline"},
}

_TIPO_ROTULO = {"primaria": "primária", "complementar": "complementar", "auxiliar": "auxiliar"}


def _registry():
    import desktop_config as cfg
    import local_data
    return cfg, local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


def _num_registros(caminho: Path, formato: str):
    """Nº de registros REAL: num_rows do rodapé Parquet (O(1)); linhas do CSV; None p/ outros."""
    try:
        if formato == "parquet":
            import pyarrow.parquet as pq
            return int(pq.ParquetFile(str(caminho)).metadata.num_rows)
        if formato == "csv":
            with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return None
    return None


def _procedencia(reg, chave: str, formato: str):
    """Lê a procedência EMBARCADA (colunas fonte_base/fonte_versao) do dado — honesto, não
    declarado. Devolve (bases, versoes) ou (None, None). Só para Parquet."""
    if formato != "parquet":
        return None, None
    try:
        df = reg.carregar_parquet(chave, colunas=["fonte_base", "fonte_versao"])
        bases = sorted(set(str(x) for x in df["fonte_base"].dropna().unique()))
        vers = sorted(set(str(x) for x in df["fonte_versao"].dropna().unique()))
        return bases or None, vers or None
    except Exception:
        return None, None


def catalogo(medir: bool = True) -> list:
    """Catálogo completo: por recurso, metadados declarados + fatos medidos. `medir`=False pula as
    leituras pesadas (procedência) — usado por UIs que precisam ser rápidas. Nunca levanta."""
    import local_data
    cfg, reg = _registry()
    linhas = []
    for d in local_data.CATALOGO:
        meta = FONTE_META.get(d.chave, {})
        inst = reg.existe(d.chave)
        item = {
            "chave": d.chave, "descricao": d.descricao, "formato": d.formato,
            "essencial": bool(d.essencial), "instalado": bool(inst),
            "organizacao": meta.get("org", "—"), "tipo_fonte": meta.get("tipo", "—"),
            "licenca": meta.get("licenca", "—"), "portal": meta.get("portal", ""),
            "finalidade": meta.get("finalidade", d.descricao),
            "caminho": str(reg.caminho(d.chave)),
        }
        if inst:
            a = reg.assinatura(d.chave)
            item["mb"] = round(a["bytes"] / (1024 ** 2), 1)
            item["hash12"] = a["hash12"]
            if medir:
                item["registros"] = _num_registros(reg.caminho(d.chave), d.formato)
                bases, vers = _procedencia(reg, d.chave, d.formato)
                item["fonte_base"] = bases
                item["fonte_versoes"] = vers
        linhas.append(item)
    return linhas


def render_texto(cat=None) -> str:
    cat = cat if cat is not None else catalogo(medir=True)
    L = ["CATÁLOGO DE DADOS NACIONAIS — OpenRotas", "=" * 64]
    for r in cat:
        marca = "✓" if r["instalado"] else "○"
        L.append("%s %s  [%s · fonte %s]" % (marca, r["chave"], r["organizacao"],
                                             _TIPO_ROTULO.get(r["tipo_fonte"], r["tipo_fonte"])))
        det = []
        if r.get("registros") is not None:
            det.append("%s reg." % r["registros"])
        if r.get("mb") is not None:
            det.append("%s MB" % r["mb"])
        if r.get("fonte_base"):
            det.append("base %s" % "/".join(r["fonte_base"]))
        if r.get("fonte_versoes"):
            det.append("versões %s" % ", ".join(r["fonte_versoes"]))
        if det:
            L.append("    " + " · ".join(det))
        L.append("    finalidade: %s | licença: %s" % (r["finalidade"], r["licenca"]))
    inst = sum(1 for r in cat if r["instalado"])
    L.append("")
    L.append("Recursos: %d instalados de %d. Procedência lida dos próprios dados; organização/"
             "licença/portal são metadados declarados." % (inst, len(cat)))
    return "\n".join(L)


def gerar_md(caminho, cat=None) -> str | None:
    """Catálogo de Dados Nacionais em Markdown (§15/§33) com tabela e rastreabilidade (§70)."""
    try:
        cat = cat if cat is not None else catalogo(medir=True)
        out = ["# Catálogo de Dados Nacionais — OpenRotas", "",
               "_Procedência (base/versão) lida dos próprios dados instalados; organização, licença "
               "e portal são metadados declarados. Nenhum dado fabricado._", "",
               "| Recurso | Organização | Fonte | Registros | Tamanho | Base | Versões | Licença |",
               "|---------|-------------|:-----:|----------:|--------:|------|---------|---------|"]
        for r in cat:
            out.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r["chave"], r["organizacao"], _TIPO_ROTULO.get(r["tipo_fonte"], r["tipo_fonte"]),
                (r.get("registros") if r.get("registros") is not None else "—"),
                ("%s MB" % r["mb"]) if r.get("mb") is not None else "—",
                "/".join(r.get("fonte_base") or []) or "—",
                ", ".join(r.get("fonte_versoes") or []) or "—",
                r["licenca"]))
        out += ["", "## Rastreabilidade (§70)", ""]
        for r in cat:
            out.append("- **%s** — %s (fonte %s). Finalidade: %s. Portal: %s" % (
                r["chave"], r["organizacao"], _TIPO_ROTULO.get(r["tipo_fonte"], r["tipo_fonte"]),
                r["finalidade"], r["portal"] or "—"))
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(out) + "\n", encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[CATALOGO] falha ao gerar o Markdown.", exc_info=True)
        return None


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cat = catalogo(medir=True)
    print(render_texto(cat))
    if "--md" in argv:
        try:
            import desktop_config as cfg
            destino = cfg.ensure_user_dirs()["exports"] / "catalogo_dados_nacionais.md"
        except Exception:
            destino = Path("catalogo_dados_nacionais.md")
        got = gerar_md(destino, cat)
        print("\nCatálogo salvo em: %s" % got if got else "\nFalha ao salvar o catálogo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
