# -*- coding: utf-8 -*-
"""
construir_grafo_hidrografia_nacional.py
=======================================
Gera o GRAFO FLUVIAL NACIONAL (`hidrografia_nacional.pkl.gz`) usado pelo roteamento fluvial da
aplicação (distância navegável real + rios nomeados + traçado) — cobrindo o BRASIL INTEIRO com a
hidrografia oficial IBGE BC250 (`hid_trecho_drenagem_l`), que é a MESMA base densa da ANA/SNIRH já
usada na DETECÇÃO de cruzamentos. Não depende de GDAL/geopandas/shapely: lê o Parquet derivado
`data/brasil/ibge/derivadas/drenagem.parquet` (2,18 mi de trechos, geometria em WKB) que o
`construir_bases_locais_ibge.py` já produziu, e monta um grafo de roteamento no FORMATO EXATO que o
app carrega em `_carregar_grafo_fluvial` (streamlit_app.py):

    {
      'coords': np.ndarray (N, 2) float64  — (lon, lat) de cada nó
      'e'     : np.ndarray (E, 2) int32    — arestas (u, v) por índice de nó (não-direcionadas)
      'w'     : np.ndarray (E,)  float32   — peso da aresta em KM (haversine entre os nós)
      'en'    : np.ndarray (E,)  int32     — índice do NOME do rio da aresta (aponta para 'names')
      'names' : list[str]                  — nomes de rio (índice 0 = '' = sem nome)
    }

COMO A COBERTURA NACIONAL É PRESERVADA E O TAMANHO É CONTROLADO
--------------------------------------------------------------
Os ~21 milhões de vértices brutos do BC250 são densos demais para carregar em memória no runtime.
O construtor faz SNAP EM GRADE (parâmetro --grid, em graus): vértices na mesma célula viram o MESMO
nó — isso (a) reduz o nº de nós e (b) CONECTA trechos que se tocam (mesmo que os vértices não sejam
idênticos), o que é essencial para o roteamento. A grade é UNIFORME em todo o país, então a
densidade natural é preservada: a Amazônia continua densa, o semiárido continua esparso — ao
contrário do artefato Natural Earth 10m anterior, que era denso no Sul/Sudeste e vazio na Amazônia.

Uso (offline, na sua máquina, com o repositório já com os Parquets derivados):
    python3 construir_grafo_hidrografia_nacional.py
    # ^ reproduz EXATAMENTE o hidrografia_nacional.pkl.gz versionado (grade 0.020, ~19 MB,
    #   ~1,47 mi de nós, ~270 MB de RAM no runtime). O app o encontra e carrega sozinho.
    python3 construir_grafo_hidrografia_nacional.py --grid 0.010   # mais fiel/pesado (~40 MB, ~1,3 GB RAM)
    # build regional (teste rápido / validação — use = por causa do sinal negativo no bbox):
    python3 construir_grafo_hidrografia_nacional.py --bbox=-6,0.5,-64,-56 --saida amazonia_teste.pkl.gz

IMPORTANTE — ORÇAMENTO DE MEMÓRIA: o grafo é CARREGADO no runtime (cKDTree + matriz esparsa) durante o
roteamento fluvial (inclusive na alocação/DECIDIR quando há município ribeirinho). Em hosts com pouca
RAM (Streamlit Community Cloud), uma grade fina demais estoura a memória e derruba a app (OOM). A grade
padrão 0.020 foi escolhida para manter ~1,47 mi de nós (≈ o grafo NE10m mundial que rodava antes) e
~270 MB de RAM. NÃO subir para 0.010/0.004 no arquivo versionado sem confirmar o limite de RAM do host.

Parâmetros principais:
    --grid   G   tamanho da célula de snap em GRAUS (padrão 0.020 ≈ 2,2 km — o valor DEPLOYADO no
                 repositório, ~1,47 mi de nós / ~19 MB / ~270 MB RAM). Menor = mais fiel e MUITO mais
                 pesado (0.010≈40 MB/~1,3 GB RAM; 0.006≈67 MB; 0.004≈89 MB/2,8 GB RAM) — pode causar OOM
                 no Streamlit Cloud. Só use grade menor com host de RAM alta e verificação.
    --bbox   lat_min,lat_max,lon_min,lon_max  recorta a construção a uma janela (opcional).
    --saida  arquivo .pkl.gz de saída (padrão hidrografia_nacional.pkl.gz — o app o encontra sozinho).
    --parquet  caminho do drenagem.parquet (padrão: data/brasil/ibge/derivadas/drenagem.parquet).
    --min-comp N  descarta componentes conexos com menos de N nós (remove lixo isolado; padrão 3).

Requer: numpy, pandas, pyarrow, scipy (todos já usados pelo app). Sem dependências binárias novas.
"""
import argparse
import gzip
import math
import os
import pickle
import sys
import time

import numpy as np

# WKB puro (sem GDAL) — reutiliza o decodificador já existente e testado do projeto.
try:
    from inteligencia_geoespacial import bases_locais as _bl
    _deco_wkb = _bl._deco_wkb
    _caminho_camada = _bl._caminho
except Exception:  # execução fora do diretório do projeto
    _bl = None
    _deco_wkb = None
    _caminho_camada = None


def _log(msg):
    print("[grafo-hidro] %s" % msg, flush=True)


def _haversine_km_vec(lon1, lat1, lon2, lat2):
    """Haversine vetorizado (km) entre arrays de (lon,lat)."""
    R = 6371.0088
    la1 = np.radians(lat1); la2 = np.radians(lat2)
    dlat = la2 - la1
    dlon = np.radians(lon2 - lon1)
    h = np.sin(dlat / 2.0) ** 2 + np.cos(la1) * np.cos(la2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * R * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def _normalizar_nome(n):
    try:
        s = str(n).strip()
    except Exception:
        return ""
    if not s or s.lower() in ("nan", "none", "null", "sem nome", "-"):
        return ""
    return s


def construir_grafo(parquet, grid=0.020, bbox=None, min_comp=3):
    """Lê o Parquet de drenagem e devolve o dict do grafo no formato do app. PURO (sem I/O de saída)."""
    import pandas as pd

    if _deco_wkb is None:
        raise RuntimeError("bases_locais indisponível — rode a partir da raiz do repositório do app.")

    filtros = None
    if bbox is not None:
        la0, la1, lo0, lo1 = bbox
        filtros = [("xmin", "<=", lo1), ("xmax", ">=", lo0), ("ymin", "<=", la1), ("ymax", ">=", la0)]

    _log("lendo %s%s ..." % (parquet, "" if bbox is None else (" (bbox %s)" % (bbox,))))
    df = pd.read_parquet(parquet, columns=["geometry_wkb", "nome"], filters=filtros)
    n_linhas = len(df)
    _log("%d trechos de drenagem carregados" % n_linhas)

    inv_grid = 1.0 / float(grid)

    node_id = {}                 # (ilon, ilat) -> id
    coords = []                  # id -> (lon, lat) do centro da célula
    names = [""]                 # 0 = sem nome
    name_id = {"": 0}
    # aresta não-direcionada (u<v) -> [n_id]  (peso é recomputado vetorizado no fim)
    edges = {}

    def _no(lon, lat):
        ilon = int(math.floor(lon * inv_grid))
        ilat = int(math.floor(lat * inv_grid))
        k = (ilon, ilat)
        i = node_id.get(k)
        if i is None:
            i = len(coords)
            node_id[k] = i
            coords.append(((ilon + 0.5) * grid, (ilat + 0.5) * grid))
        return i

    t0 = time.time()
    wkbs = df["geometry_wkb"].to_numpy()
    noms = df["nome"].to_numpy()
    for _idx in range(n_linhas):
        try:
            pts = _deco_wkb(wkbs[_idx])
        except Exception:
            pts = None
        if not pts or not isinstance(pts, list) or not isinstance(pts[0], tuple):
            continue  # só LINESTRING (drenagem é linha)
        nm = _normalizar_nome(noms[_idx])
        nid = name_id.get(nm)
        if nid is None:
            nid = len(names); names.append(nm); name_id[nm] = nid
        prev = None
        for (lon, lat) in pts:
            try:
                u = _no(float(lon), float(lat))
            except Exception:
                prev = None
                continue
            if prev is not None and prev != u:
                a, b = (prev, u) if prev < u else (u, prev)
                ex = edges.get((a, b))
                if ex is None:
                    edges[(a, b)] = nid
                elif ex == 0 and nid != 0:
                    edges[(a, b)] = nid   # prefere aresta NOMEADA quando houver conflito
            prev = u
        if _idx % 200000 == 0 and _idx:
            _log("  %d/%d trechos · %d nós · %d arestas · %.0fs"
                 % (_idx, n_linhas, len(coords), len(edges), time.time() - t0))

    _log("bruto: %d nós, %d arestas, %d nomes" % (len(coords), len(edges), len(names)))

    coords = np.asarray(coords, dtype=np.float64)
    if len(edges) == 0:
        raise RuntimeError("nenhuma aresta gerada — parquet vazio ou bbox sem drenagem")
    e = np.fromiter((x for ab in edges.keys() for x in ab), dtype=np.int64,
                    count=2 * len(edges)).reshape(-1, 2)
    en = np.fromiter(edges.values(), dtype=np.int64, count=len(edges))

    # poda de componentes conexos minúsculos (lixo isolado) — mantém a navegabilidade real
    if min_comp and min_comp > 1:
        coords, e, en, names = _podar_componentes(coords, e, en, names, min_comp)

    # pesos = haversine (km) entre os nós de cada aresta
    w = _haversine_km_vec(coords[e[:, 0], 0], coords[e[:, 0], 1],
                          coords[e[:, 1], 0], coords[e[:, 1], 1]).astype(np.float32)

    return {"coords": coords.astype(np.float64),
            "e": e.astype(np.int32),
            "w": w,
            "en": en.astype(np.int32),
            "names": names}


def _podar_componentes(coords, e, en, names, min_comp):
    """Remove nós/arestas de componentes conexos com < min_comp nós e reindexa. Defensivo."""
    try:
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import connected_components
    except Exception:
        return coords, e, en, names
    n = len(coords)
    row = np.concatenate([e[:, 0], e[:, 1]])
    col = np.concatenate([e[:, 1], e[:, 0]])
    dat = np.ones(len(row), dtype=np.int8)
    g = csr_matrix((dat, (row, col)), shape=(n, n))
    ncomp, labels = connected_components(g, directed=False)
    tam = np.bincount(labels, minlength=ncomp)
    manter_no = tam[labels] >= int(min_comp)
    if manter_no.all():
        return coords, e, en, names
    novo_id = -np.ones(n, dtype=np.int64)
    keep_idx = np.nonzero(manter_no)[0]
    novo_id[keep_idx] = np.arange(len(keep_idx))
    keep_e = manter_no[e[:, 0]] & manter_no[e[:, 1]]
    e2 = novo_id[e[keep_e]]
    en2 = en[keep_e]
    coords2 = coords[keep_idx]
    _log("poda: %d→%d nós, %d→%d arestas (componentes < %d removidos)"
         % (n, len(coords2), len(e), len(e2), min_comp))
    return coords2, e2, en2, names


def _validar(g):
    """Confere o formato e a integridade referencial do grafo montado. Levanta em caso de erro."""
    assert set(("coords", "e", "w", "en", "names")) <= set(g), "chaves faltando"
    C, e, w, en, names = g["coords"], g["e"], g["w"], g["en"], g["names"]
    N = len(C)
    assert C.ndim == 2 and C.shape[1] == 2, "coords deve ser (N,2)"
    assert e.ndim == 2 and e.shape[1] == 2 and len(e) == len(w) == len(en), "e/w/en incompatíveis"
    assert e.min() >= 0 and e.max() < N, "índice de nó fora de faixa"
    assert en.min() >= 0 and en.max() < len(names), "índice de nome fora de faixa"
    lon, lat = C[:, 0], C[:, 1]
    dentro = ((lon >= -74) & (lon <= -34) & (lat >= -34) & (lat <= 6)).mean()
    _log("validação OK · %d nós · %d arestas · %d nomes · %.1f%% dos nós dentro do Brasil"
         % (N, len(e), len(names), 100.0 * dentro))


def salvar(g, saida):
    tmp = saida + ".tmp"
    with gzip.open(tmp, "wb", compresslevel=6) as fh:
        pickle.dump(g, fh, protocol=4)
    os.replace(tmp, saida)
    _log("salvo: %s (%.1f MB)" % (saida, os.path.getsize(saida) / 1e6))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Constrói o grafo fluvial nacional (IBGE BC250/ANA).")
    ap.add_argument("--parquet", default=None, help="caminho do drenagem.parquet")
    ap.add_argument("--saida", default="hidrografia_nacional.pkl.gz")
    ap.add_argument("--grid", type=float, default=0.020,
                    help="célula de snap em graus (padrão 0.020 ≈ 2,2 km — o valor deployado; ~1,47 mi de "
                         "nós / ~19 MB / ~270 MB de RAM, dentro do orçamento do Streamlit Cloud)")
    ap.add_argument("--bbox", default=None, help="lat_min,lat_max,lon_min,lon_max (opcional)")
    ap.add_argument("--min-comp", type=int, default=3, help="descarta componentes com < N nós")
    a = ap.parse_args(argv)

    parquet = a.parquet
    if not parquet:
        if _caminho_camada is None:
            _log("ERRO: rode a partir da raiz do repositório, ou passe --parquet.")
            return 2
        parquet = _caminho_camada("drenagem")
    if not os.path.exists(parquet):
        _log("ERRO: parquet não encontrado: %s (gere com construir_bases_locais_ibge.py)" % parquet)
        return 2

    bbox = None
    if a.bbox:
        try:
            bbox = tuple(float(x) for x in a.bbox.split(","))
            assert len(bbox) == 4
        except Exception:
            _log("ERRO: --bbox deve ser 'lat_min,lat_max,lon_min,lon_max'")
            return 2

    t0 = time.time()
    g = construir_grafo(parquet, grid=a.grid, bbox=bbox, min_comp=a.min_comp)
    _validar(g)
    salvar(g, a.saida)
    _log("concluído em %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
