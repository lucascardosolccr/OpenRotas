# -*- coding: utf-8 -*-
"""OpenRotas Desktop — GRAFO TOPOLÓGICO e CONECTIVIDADE (§43/§7/§8).

Constrói um grafo NÓS↔ARESTAS real a partir da geometria (WKB) de uma malha (rodoviária por
padrão; aceita drenagem/ferrovias) e analisa a CONECTIVIDADE:

  • extrai as EXTREMIDADES de cada feição (início/fim do LineString/MultiLineString) do WKB;
  • faz SNAP das extremidades a uma grade (precisão em casas decimais ~ tolerância) → nós;
  • une as duas pontas de cada feição num Union-Find → componentes conexos;
  • relata: nós, arestas, componentes, % de nós no MAIOR componente (saúde da conexão),
    componentes pequenos (fragmentos), nós de grau 1 (pontas soltas).

Detecta "regiões isoladas indevidamente", nós isolados, fragmentação (§43). Honesto quanto ao
método: conectividade por SNAP de extremidades (tolerância = precisão); pontes/viadutos sem nó
compartilhado podem aparecer como componentes distintos — por isso reportamos a tolerância usada.
Stdlib + numpy; parsing de WKB sem shapely. Puro/defensivo: nunca levanta."""
from __future__ import annotations

import sys
import struct
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.grafo")

CAMADAS_OK = ("rodovias", "ferrovias", "drenagem", "hidrovias")


def _reg():
    import desktop_config as cfg
    import local_data
    return local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


def _extremidades_wkb(b):
    """(x0,y0,xe,ye) das extremidades de um WKB LineString(2)/MultiLineString(5). None se falhar."""
    try:
        b = bytes(b)
        order = "<" if b[0] == 1 else ">"
        gtype = struct.unpack(order + "I", b[1:5])[0]
        if gtype == 2:                                   # LineString
            n = struct.unpack(order + "I", b[5:9])[0]
            if n < 1:
                return None
            x0, y0 = struct.unpack(order + "dd", b[9:25])
            off = 9 + (n - 1) * 16
            xe, ye = struct.unpack(order + "dd", b[off:off + 16])
            return x0, y0, xe, ye
        if gtype == 5:                                   # MultiLineString
            ng = struct.unpack(order + "I", b[5:9])[0]
            if ng < 1:
                return None
            # início = 1º ponto da 1ª parte; fim = último ponto da última parte.
            pos = 9
            prim = None
            ult = None
            for _ in range(ng):
                o2 = "<" if b[pos] == 1 else ">"
                n = struct.unpack(o2 + "I", b[pos + 5:pos + 9])[0]
                base = pos + 9
                sx, sy = struct.unpack(o2 + "dd", b[base:base + 16])
                eoff = base + (n - 1) * 16
                ex, ey = struct.unpack(o2 + "dd", b[eoff:eoff + 16])
                if prim is None:
                    prim = (sx, sy)
                ult = (ex, ey)
                pos = base + n * 16
            if prim and ult:
                return prim[0], prim[1], ult[0], ult[1]
        return None
    except Exception:
        return None


def _endpoints(reg, camada: str, limite=None):
    """Arrays numpy (x0,y0,xe,ye) das extremidades de cada feição da camada. Nunca levanta."""
    import numpy as np
    df = reg.carregar_parquet(camada, colunas=["geometry_wkb"])
    col = df["geometry_wkb"]
    if limite:
        col = col.iloc[:limite]
    x0 = []; y0 = []; xe = []; ye = []
    for b in col:
        r = _extremidades_wkb(b)
        if r is None:
            continue
        x0.append(r[0]); y0.append(r[1]); xe.append(r[2]); ye.append(r[3])
    return (np.array(x0), np.array(y0), np.array(xe), np.array(ye))


class _UF:
    """Union-Find com compressão de caminho e união por tamanho."""
    def __init__(self, n):
        self.p = list(range(n))
        self.sz = [1] * n

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.sz[ra] < self.sz[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        self.sz[ra] += self.sz[rb]


def construir(camada: str = "rodovias", precisao: int = 3, limite=None) -> dict:
    """Constrói o grafo e analisa a conectividade. precisao=casas decimais do snap (3≈100 m).
    Devolve o laudo. Nunca levanta."""
    base = {"camada": camada, "precisao": precisao, "arestas": 0, "nos": 0, "componentes": 0,
            "maior_componente_nos": 0, "pct_maior": 0.0, "componentes_pequenos": 0,
            "nos_grau1": 0, "status": "AUSENTE"}
    try:
        reg = _reg()
        if not reg.existe(camada):
            return base
        import numpy as np
        x0, y0, xe, ye = _endpoints(reg, camada, limite=limite)
        m = len(x0)
        if m == 0:
            return base
        # snap → chave inteira de nó (evita float como chave).
        f = 10 ** precisao
        kx0 = np.rint(x0 * f).astype("int64"); ky0 = np.rint(y0 * f).astype("int64")
        kxe = np.rint(xe * f).astype("int64"); kye = np.rint(ye * f).astype("int64")
        # ids de nó via dict de tuplas.
        nodo = {}
        def _id(kx, ky):
            k = (int(kx), int(ky))
            i = nodo.get(k)
            if i is None:
                i = len(nodo); nodo[k] = i
            return i
        a_ids = np.empty(m, dtype="int64"); b_ids = np.empty(m, dtype="int64")
        grau = {}
        for i in range(m):
            ia = _id(kx0[i], ky0[i]); ib = _id(kxe[i], kye[i])
            a_ids[i] = ia; b_ids[i] = ib
            grau[ia] = grau.get(ia, 0) + 1
            grau[ib] = grau.get(ib, 0) + 1
        nnos = len(nodo)
        uf = _UF(nnos)
        for i in range(m):
            uf.union(int(a_ids[i]), int(b_ids[i]))
        # tamanho dos componentes (por raiz).
        tam = {}
        for v in range(nnos):
            r = uf.find(v)
            tam[r] = tam.get(r, 0) + 1
        tamanhos = sorted(tam.values(), reverse=True)
        maior = tamanhos[0] if tamanhos else 0
        base.update({
            "arestas": int(m), "nos": int(nnos), "componentes": int(len(tamanhos)),
            "maior_componente_nos": int(maior),
            "pct_maior": round(100.0 * maior / nnos, 2) if nnos else 0.0,
            "componentes_pequenos": int(sum(1 for t in tamanhos if t <= 2)),
            "nos_grau1": int(sum(1 for g in grau.values() if g == 1)),
            "status": "OK",
        })
        return base
    except Exception:
        logger.warning("[GRAFO] construção de %r falhou.", camada, exc_info=True)
        return base


def render_texto(g: dict) -> str:
    if g.get("status") == "AUSENTE":
        return "Grafo topológico indisponível para %r (camada ausente)." % g.get("camada")
    L = ["GRAFO TOPOLÓGICO — %s" % g["camada"], "=" * 52,
         "arestas (feições): %d" % g["arestas"],
         "nós (após snap ~%d casas): %d" % (g["precisao"], g["nos"]),
         "componentes conexos: %d" % g["componentes"],
         "maior componente: %d nós (%.2f%% do total)" % (g["maior_componente_nos"], g["pct_maior"]),
         "componentes pequenos (≤2 nós): %d" % g["componentes_pequenos"],
         "nós de grau 1 (pontas soltas): %d" % g["nos_grau1"],
         "",
         "Conectividade por snap de extremidades (tolerância = precisão). Um % alto no maior",
         "componente indica malha bem conectada; muitos componentes pequenos = fragmentação."]
    return "\n".join(L)


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    camada = "rodovias"
    precisao = 3
    limite = None
    for a in argv:
        if a in CAMADAS_OK:
            camada = a
        elif a.startswith("--precisao="):
            try:
                precisao = int(a.split("=", 1)[1])
            except Exception:
                pass
        elif a.startswith("--limite="):
            try:
                limite = int(a.split("=", 1)[1])
            except Exception:
                pass
    print(render_texto(construir(camada, precisao=precisao, limite=limite)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
