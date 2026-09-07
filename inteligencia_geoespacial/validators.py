"""
Validators - validação cruzada de coordenadas contra as bases oficiais locais.

Consome as camadas derivadas IBGE (inteligencia_geoespacial/bases_locais) para
responder a perguntas de auditoria geográfica sem nenhuma chamada de rede:

    CoordinateValidator()            validar ponto contra camadas locais
      .municipio(lat, lon)           município IBGE do ponto (point-in-polygon)
      .mais_proximas(camada, ...)    feições da camada a até raio_km
      .rio_mais_proximo(...)         drenagem nomeada mais próxima (+navegável)
      .perfil(...)                   pacote: município + rio + feições + confiança
      .confianca(perfil)             pontuação 0-100 e fontes que concordam
      .validar_trecho(orig, dest)    valida ambos os pontos e cruza as fontes
"""

from __future__ import annotations

from . import bases_locais as _bl

# Camadas de infraestrutura consultadas no perfil padrão (leves, com nome).
_CAMADAS_INFRA = (
    "pontes",
    "travessias",
    "eclusas",
    "atracadouros_terminal",
    "complexos_portuarios",
    "hidrovias",
)

_ATRIBUTOS_DIGEST = {
    "pontes": "tipoponte",
    "travessias": "tipotraves",
    "eclusas": "operaciona",
    "atracadouros_terminal": "tipoatraca",
    "complexos_portuarios": "jurisdicao",
    "hidrovias": "regime",
}

_NIVEL_CONFIANCA = (("alta", 70), ("media", 40))


def _nome(v) -> str:
    """Normaliza valores textuais das camadas (NaN do pandas → '')."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


class CoordinateValidator:
    """Auditoria geoespacial de coordenadas usando apenas bases locais (IBGE)."""

    def __init__(self, raio_km: float = 30.0, limite: int = 5):
        self.raio_km = float(raio_km)
        self.limite = int(limite)

    # ------------------------------------------------------------------ base
    def municipio(self, lat: float, lon: float) -> dict:
        return _bl.municipio_do_ponto(float(lat), float(lon))

    def mais_proximas(self, camada: str, lat: float, lon: float,
                      raio_km: float | None = None, limite: int | None = None,
                      filtros: dict | None = None) -> list:
        return _bl.mais_proximos(
            camada, float(lon), float(lat),
            raio_km=float(raio_km if raio_km is not None else self.raio_km),
            limite=int(limite if limite is not None else self.limite),
            filtros=filtros,
        )

    def rio_mais_proximo(self, lat: float, lon: float,
                         raio_km: float | None = None) -> dict | None:
        """Drenagem NOMEADA (rio/igarapé/córrego) mais próxima do ponto."""
        raio = float(raio_km if raio_km is not None else max(self.raio_km, 30.0))
        rows = _bl.mais_proximos(
            "drenagem", float(lon), float(lat), raio_km=raio,
            limite=max(self.limite * 4, 20),
        )
        for r in rows:
            nome = _nome(r.get("nome"))
            if not nome:
                continue
            return {
                "nome": nome,
                "distancia_km": round(float(r["distancia_km"]), 2),
                "navegavel": _nome(r.get("navegavel")) or "Desconhecido",
                "regime": _nome(r.get("regime")) or "Desconhecido",
                "camada": "drenagem",
                "fonte": "IBGE BC250/BC100 (drenagem)",
            }
        return None

    # ------------------------------------------------------------------ perfil
    def perfil(self, lat: float, lon: float, raio_km: float | None = None,
               camadas: tuple = _CAMADAS_INFRA) -> dict:
        """Pacote completo: município + rio mais próximo + feições de cada camada
        (digest compacto) + quantidades. Sem pontuação (ver .confianca)."""
        la, lo = float(lat), float(lon)
        raio = float(raio_km if raio_km is not None else self.raio_km)
        feicoes = {}
        for camada in camadas:
            items = self.mais_proximas(camada, la, lo, raio_km=raio)
            digest = []
            for it in items:
                d = {
                    "nome": _nome(it.get("nome")) or "<sem nome>",
                    "distancia_km": round(float(it["distancia_km"]), 2),
                    "tipo_geom": it.get("tipo_geom"),
                }
                chave = _ATRIBUTOS_DIGEST.get(camada)
                if chave:
                    atributo = _nome(it.get(chave))
                    if atributo:
                        d["atributo"] = atributo
                digest.append(d)
            feicoes[camada] = digest
        return {
            "municipio": self.municipio(la, lo),
            "rio_mais_proximo": self.rio_mais_proximo(la, lo, raio_km=raio),
            "feicoes": feicoes,
            "quantidades": {c: len(v) for c, v in feicoes.items()},
            "raio_km": raio,
            "parametros": {"lat": la, "lon": lo},
        }

    # ------------------------------------------------------------- confiança
    def confianca(self, perfil: dict) -> dict:
        """Pontua 0-100 a validade geográfica do ponto com base no perfil.

        Fontes que concordam (aditivo, auditável):
          - IBGE (malha municipal) · hidrografia BC · travessias · pontes · portos/eclusas
        """
        pts = 0
        fontes = []

        if perfil.get("municipio"):
            pts += 40
            fontes.append("IBGE (malha municipal)")
            if perfil["municipio"].get("geocodigo"):
                pts += 5

        rio = perfil.get("rio_mais_proximo")
        if rio and rio.get("distancia_km") <= perfil.get("raio_km", 30.0):
            pts += 20
            fontes.append("IBGE BC250/BC100 (hidrografia)")
            navegavel = (rio.get("navegavel") or "").strip().lower()
            if navegavel in ("sim", "parcial"):
                pts += 10
                fontes.append("IBGE BC250 (navegável)")

        q = perfil.get("quantidades", {})
        if q.get("travessias", 0) or q.get("atracadouros_terminal", 0) or \
           q.get("complexos_portuarios", 0) or q.get("eclusas", 0):
            pts += 20
            fontes.append("IBGE BC250 (infraestrutura aquaviária)")

        if q.get("pontes", 0):
            pts += 10
            fontes.append("IBGE BC250 (pontes)")

        pts = max(0, min(100, pts))
        nivel = "baixa"
        for nome, lim in _NIVEL_CONFIANCA:
            if pts >= lim:
                nivel = nome
                break
        return {
            "pontuacao": pts,
            "nivel": nivel,
            "fontes_concordam": sorted(set(fontes)),
            "motivo": ("Válido em %d fonte(s) independentes (%s)." % (len(fontes), ", ".join(fontes) or "nenhuma")),
        }

    def confianca_para(self, lat: float, lon: float,
                       raio_km: float | None = None) -> dict:
        p = self.perfil(lat, lon, raio_km=raio_km)
        c = self.confianca(p)
        return {"perfil": p, "confianca": c}

    # ------------------------------------------------------------------ trecho
    def validar_trecho(self, origem: tuple, destino: tuple,
                       raio_km: float | None = None) -> dict:
        """Valida origem e destino e cruza as fontes que concordam nos dois."""
        o = self.perfil(float(origem[0]), float(origem[1]), raio_km=raio_km)
        d = self.perfil(float(destino[0]), float(destino[1]), raio_km=raio_km)
        co = self.confianca(o)
        cd = self.confianca(d)
        comum = sorted(set(co["fontes_concordam"]) & set(cd["fontes_concordam"]))
        return {
            "origem": {"perfil": o, "confianca": co},
            "destino": {"perfil": d, "confianca": cd},
            "fontes_comuns": comum,
            "niveis": {
                "origem": co["nivel"],
                "destino": cd["nivel"],
            },
        }