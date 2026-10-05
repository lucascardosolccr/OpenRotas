# -*- coding: utf-8 -*-
"""OpenRotas Desktop — GeoIntelligenceRepository + consultas multimodais (§24/§25/§6/§8).

Camada UNIFICADA de inteligência geoespacial da edição desktop: um único ponto que carrega
(preguiçosamente, §16) as bases nacionais instaladas e responde consultas espaciais rápidas,
para que NENHUM módulo precise reprocessar as mesmas geometrias (§24). O índice é feito sobre as
colunas de CAIXA ENVOLVENTE (xmin/ymin/xmax/ymax) e o ponto representativo (lon/lat) que TODA base
derivada já traz — consultas vetorizadas em numpy, sem depender de shapely/geopandas e sem carregar
geometria pesada (§25/§55/§56). É, portanto, um índice de nível BBOX: honesto e explicitamente
aproximado (não faz interseção geométrica exata), mas suficiente para "o que existe perto/na rota".

Consultas (§6):
  • proximidade(camada, lon, lat, raio)         — feições perto de um ponto;
  • intersecta_bbox(camada, x0,y0,x1,y1)        — feições cuja bbox cruza uma janela;
  • contar_na_rota(coords, camadas, folga)      — por trecho da rota, conta feições por camada
                                                  (responde "quais rios/pontes/travessias na rota?").
Multimodal (§8):
  • inventario_multimodal()                     — nós/arestas por modal + presença;
  • analise_multimodal_rota(coords)             — cruzamentos por modal ao longo da rota.

Defensivo: nunca levanta; cada consulta degrada para vazio. Cache em memória por camada."""
from __future__ import annotations

import sys
import math
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent / "app", _AQUI.parent, _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo")

# Camadas (modais) e sua classe multimodal — para o inventário/análise §8.
MODAIS = {
    "rodovias": "rodoviario",
    "ferrovias": "ferroviario",
    "drenagem": "fluvial",
    "hidrovias": "aquaviario",
    "massas_dagua": "hidrico",
    "pontes": "transposicao",
    "travessias": "transposicao",
    "eclusas": "aquaviario",
    "atracadouros_terminal": "aquaviario",
    "complexos_portuarios": "portuario",
}

_GRAU_KM = 111.0  # 1° ~ 111 km (aprox., para converter raios km↔graus de forma honesta/aproximada)


def _registry():
    import desktop_config as cfg
    import local_data
    return local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


class GeoIntelligenceRepository:
    """Repositório unificado com cache dos arrays espaciais por camada (§24)."""

    def __init__(self, registry=None):
        self.reg = registry or _registry()
        self._arrays: dict = {}

    # ---- carregamento preguiçoso dos arrays espaciais (bbox + ponto) ----
    def arrays(self, camada: str):
        """Dict de arrays numpy {lon,lat,xmin,ymin,xmax,ymax} da camada (cacheado). None se a
        camada não existe/não abre. Lê SÓ as 6 colunas espaciais (projeção) — leve mesmo em
        bases de milhões de linhas (§16/§56)."""
        if camada in self._arrays:
            return self._arrays[camada]
        if not self.reg.existe(camada):
            self._arrays[camada] = None
            return None
        try:
            import numpy as np
            df = self.reg.carregar_parquet(camada, colunas=["lon", "lat", "xmin", "ymin", "xmax", "ymax"])
            a = {k: df[k].to_numpy(dtype="float64", copy=False) for k in
                 ("lon", "lat", "xmin", "ymin", "xmax", "ymax")}
            a["n"] = int(len(df))
            self._arrays[camada] = a
            return a
        except Exception:
            logger.warning("[GEO] falha ao carregar arrays de %r.", camada, exc_info=True)
            self._arrays[camada] = None
            return None

    def liberar(self):
        self._arrays.clear()

    def disponivel(self, camada: str) -> bool:
        a = self.arrays(camada)
        return bool(a and a["n"] > 0)

    # ---- consultas espaciais (nível bbox, vetorizadas) ----
    def intersecta_bbox(self, camada: str, x0, y0, x1, y1):
        """Índices das feições cuja CAIXA ENVOLVENTE cruza a janela (x0,y0,x1,y1). np.ndarray
        (possivelmente vazio). Usa separating-axis em bbox: NÃO se cruzam sse uma está toda à
        esquerda/direita/acima/abaixo da outra."""
        import numpy as np
        a = self.arrays(camada)
        if not a or a["n"] == 0:
            return np.empty(0, dtype="int64")
        qx0, qx1 = (x0, x1) if x0 <= x1 else (x1, x0)
        qy0, qy1 = (y0, y1) if y0 <= y1 else (y1, y0)
        fora = (a["xmax"] < qx0) | (a["xmin"] > qx1) | (a["ymax"] < qy0) | (a["ymin"] > qy1)
        return np.nonzero(~fora)[0]

    def proximidade(self, camada: str, lon, lat, raio_km: float = 10.0) -> dict:
        """Feições cuja bbox está dentro de um quadrado de ~raio_km ao redor do ponto. Devolve
        {camada, total, raio_km}. Aproximado (bbox + grau≈111km). Nunca levanta."""
        try:
            r = max(0.0, float(raio_km)) / _GRAU_KM
            idx = self.intersecta_bbox(camada, lon - r, lat - r, lon + r, lat + r)
            return {"camada": camada, "total": int(idx.size), "raio_km": raio_km}
        except Exception:
            return {"camada": camada, "total": 0, "raio_km": raio_km}

    def _bbox_rota(self, coords):
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return min(xs), min(ys), max(xs), max(ys)

    def contar_na_rota(self, coords, camadas=None, folga_km: float = 2.0) -> dict:
        """Para uma polilinha [(lon,lat),...], conta feições de cada camada que cruzam o CORREDOR
        da rota (união das bboxes de cada trecho, com `folga_km` de margem). Responde §6: "quais
        rios/pontes/travessias a rota cruza?". Devolve {camada: n_feicoes}. Honesto/aproximado
        (nível bbox). Nunca levanta; camadas ausentes saem com 0 e flag."""
        import numpy as np
        camadas = list(camadas or [c for c in MODAIS if c != "massas_dagua"])
        out = {}
        if not coords or len(coords) < 1:
            return {c: {"feicoes": 0, "disponivel": self.disponivel(c)} for c in camadas}
        folga = max(0.0, float(folga_km)) / _GRAU_KM
        # pares de trechos (ou o ponto único)
        trechos = list(zip(coords[:-1], coords[1:])) or [(coords[0], coords[0])]
        for cam in camadas:
            if not self.disponivel(cam):
                out[cam] = {"feicoes": 0, "disponivel": False}
                continue
            acc = None
            for (lon0, lat0), (lon1, lat1) in trechos:
                idx = self.intersecta_bbox(cam, min(lon0, lon1) - folga, min(lat0, lat1) - folga,
                                           max(lon0, lon1) + folga, max(lat0, lat1) + folga)
                acc = idx if acc is None else np.union1d(acc, idx)
            out[cam] = {"feicoes": int(acc.size if acc is not None else 0), "disponivel": True}
        return out

    # ---- multimodal (§8) ----
    def inventario_multimodal(self) -> dict:
        """Inventário dos modais instalados: por camada, nº de feições ("arestas") e a classe
        multimodal; e o conjunto de classes presentes. Base honesta do 'grafo multimodal' (§8) —
        é um INVENTÁRIO + consulta on-route; a topologia completa (nós compartilhados entre modais)
        é um passo seguinte. Nunca levanta."""
        cam = {}
        classes = {}
        for c, classe in MODAIS.items():
            a = self.arrays(c)
            n = int(a["n"]) if a else 0
            inst = bool(a and n > 0)
            cam[c] = {"classe": classe, "feicoes": n, "instalado": inst}
            if inst:
                classes.setdefault(classe, 0)
                classes[classe] += n
        return {"camadas": cam, "classes": classes,
                "classes_presentes": sorted(classes.keys()),
                "total_feicoes": sum(v["feicoes"] for v in cam.values())}

    def analise_multimodal_rota(self, coords, folga_km: float = 2.0) -> dict:
        """Cruzamentos por MODAL ao longo da rota (§8/§29): agrega contar_na_rota por classe
        multimodal e devolve destaques (rios, pontes, travessias, hidrovias). Nunca levanta."""
        det = self.contar_na_rota(coords, camadas=list(MODAIS.keys()), folga_km=folga_km)
        por_classe = {}
        for cam, info in det.items():
            classe = MODAIS.get(cam, "outro")
            por_classe.setdefault(classe, 0)
            por_classe[classe] += int(info.get("feicoes", 0))
        return {
            "por_camada": det,
            "por_classe": por_classe,
            "cruza_rio": det.get("drenagem", {}).get("feicoes", 0) > 0,
            "cruza_hidrovia": det.get("hidrovias", {}).get("feicoes", 0) > 0,
            "pontes_no_corredor": det.get("pontes", {}).get("feicoes", 0),
            "travessias_no_corredor": det.get("travessias", {}).get("feicoes", 0),
            "nota": "contagem por bbox (corredor da rota), aproximada — não é interseção geométrica exata",
        }


# ---------------------------------------------------------------------------
# Render/CLI do inventário multimodal (§8/§39).
# ---------------------------------------------------------------------------
def render_inventario(inv: dict) -> str:
    L = ["INVENTÁRIO MULTIMODAL NACIONAL — OpenRotas", "=" * 52]
    cam = inv.get("camadas", {})
    for c, info in cam.items():
        marca = "✓" if info["instalado"] else "✗"
        L.append("  %s %-24s %-12s %10d feições" % (marca, c, info["classe"],
                                                    info["feicoes"] if info["instalado"] else 0))
    L.append("")
    L.append("Classes multimodais presentes: %s" % ", ".join(inv.get("classes_presentes", [])) or "—")
    L.append("Total de feições (todos os modais): %d" % inv.get("total_feicoes", 0))
    L.append("Nota: 'arestas' = feições de cada modal; o grafo multimodal consulta estes modais de "
             "forma unificada (consultas on-route por corredor/bbox).")
    return "\n".join(L)


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    repo = GeoIntelligenceRepository()
    inv = repo.inventario_multimodal()
    print(render_inventario(inv))
    # Demonstração honesta on-route se o usuário passar coords "lon,lat;lon,lat;..."
    for a in argv:
        if ";" in a and "," in a:
            try:
                coords = [tuple(float(x) for x in par.split(",")) for par in a.split(";") if par]
                res = repo.analise_multimodal_rota(coords)
                print("\nAnálise multimodal da rota (%d pontos):" % len(coords))
                for classe, n in sorted(res["por_classe"].items()):
                    print("  %-14s %d" % (classe, n))
                print("  %s" % res["nota"])
            except Exception as e:
                print("coords inválidas (%s): %s" % (a, e))
    return 0 if inv.get("total_feicoes", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
