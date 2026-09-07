"""
IBGE Derivadas Provider - adaptador unificado das camadas derivadas locais do IBGE.

Implementa o contrato `BaseProvider` (fetch → validate → transform → to_geojson)
sobre `inteligencia_geoespacial/bases_locais`, que consulta os Parquet locais
(BC250/BC100) sem rede e sem GDAL/geopandas/shapely.

Uso típico:
    p = IBGEDerivadasProvider(source_id="ibge_der_travessias")
    dados = p.fetch_with_cache(camada="travessias", lat=-3.1, lon=-60.0,
                               raio_km=50, limite=10, filtros={"tipotraves": "Balsa"})
    fc = p.to_geojson(dados)

Camada especial "municipios" retorna o município que contém o ponto (point-in-polygon).
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from pathlib import Path

from .base import BaseProvider
from .exceptions import ProviderValidationException

_FIXAS = frozenset({
    "geometry_wkb", "lon", "lat", "xmin", "ymin", "xmax", "ymax",
    "tipo_geom", "fonte_base", "fonte_uf", "fonte_versao", "distancia_km",
})


def wkb_para_geojson(wkb: bytes | None) -> dict | None:
    """Converte WKB big/little-endian (camadas locais) para geometria GeoJSON."""
    if wkb is None:
        return None
    from ..bases_locais import _deco_wkb

    g = _deco_wkb(wkb)
    if g is None:
        return None
    if isinstance(g, tuple):
        return {"type": "Point", "coordinates": [g[0], g[1]]}
    if g and isinstance(g[0], list):
        return {"type": "Polygon", "coordinates": [[[x, y] for (x, y) in ring] for ring in g]}
    return {"type": "LineString", "coordinates": [[x, y] for (x, y) in g]}


class IBGEDerivadasProvider(BaseProvider):
    """Provider unificado para as 12 camadas derivadas IBGE (Parquet locais)."""

    TIPOS = ("pontes", "travessias", "hidrovias", "atracadouros_terminal",
             "complexos_portuarios", "eclusas", "sinalizacao", "rodovias",
             "ferrovias", "massas_dagua", "drenagem", "municipios")

    def __init__(self, source_id: str = "ibge_der_travessias",
                 name: Optional[str] = None, cache_dir: Optional[Path] = None,
                 cache_ttl_hours: int = 168):
        super().__init__(name or "IBGE - Camadas Derivadas (BC250/BC100)",
                         source_id, cache_dir, cache_ttl_hours)
        self.camada_padrao = next(
            (c for c in self.TIPOS if c in source_id), "travessias")

    # ------------------------------------------------------------------ fetch
    def fetch(self, lat: float | None = None, lon: float | None = None,
              camada: str | None = None, raio_km: float = 30.0, limite: int = 10,
              filtros: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        """Busca feições da camada local a até raio_km de (lat, lon).

        Argamassa especial: camada="municipios" resolve point-in-polygon.
        """
        from .. import bases_locais

        if lat is None or lon is None:
            raise ProviderValidationException("lat e lon são obrigatórios")
        camada = camada or self.camada_padrao
        if camada not in self.TIPOS:
            raise ProviderValidationException(
                "Camada %r desconhecida. Disponíveis: %s" % (camada, ", ".join(self.TIPOS)))

        if camada == "municipios":
            mun = bases_locais.municipio_do_ponto(float(lat), float(lon))
            return [mun] if mun else []

        return bases_locais.mais_proximos(
            camada, float(lon), float(lat),
            raio_km=float(raio_km), limite=int(limite), filtros=filtros)

    # ---------------------------------------------------------------- validate
    def validate(self, data: List[Dict[str, Any]]) -> bool:
        if not isinstance(data, list):
            raise ProviderValidationException("Esperava lista de feições")
        for it in data:
            if not isinstance(it, dict):
                raise ProviderValidationException("Item não-dict na resposta")
            if not (it.get("geometry_wkb") or it.get("geocodigo") or it.get("nome")):
                raise ProviderValidationException(
                    "Item sem geometria/código/nome: %s" % str(it)[:80])
        return True

    # ---------------------------------------------------------------- transform
    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        saida = []
        for i, it in enumerate(data):
            lat = it.get("lat")
            lon = it.get("lon")
            geo = wkb_para_geojson(it.get("geometry_wkb"))
            attrs = {k: v for k, v in it.items()
                     if k not in _FIXAS and k not in ("geocodigo", "nome", "fonte_uf", "fonte_base", "fonte_versao", "tipo_geom")}
            saida.append({
                "id": "%s:%d" % (self.source_id, i),
                "codigo_ibge": str(it.get("geocodigo") or ""),
                "nome": (str(it.get("nome") or "") if it.get("nome") is not None else ""),
                "uf": it.get("fonte_uf") or "",
                "regiao": None,
                "geometria": geo,
                "coordenadas": ([float(lon), float(lat)] if lon is not None and lat is not None else None),
                "distancia_km": float(it["distancia_km"]) if it.get("distancia_km") is not None else None,
                "metadados": {
                    "camada": self.camada_padrao,
                    "tipo_geom": it.get("tipo_geom"),
                    "fonte_base": it.get("fonte_base"),
                    "fonte_versao": it.get("fonte_versao"),
                    "atributos": attrs,
                },
                "source": self.source_id,
            })
        return saida

    # ---------------------------------------------------------------- geojson
    def to_geojson(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        feats = []
        for it in data:
            geo = it.get("geometria")
            if not geo:
                continue
            props = {k: v for k, v in it.items() if k not in ("geometria", "coordenadas")}
            feats.append({"type": "Feature", "properties": props, "geometry": geo})
        return {"type": "FeatureCollection", "features": feats}