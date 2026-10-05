# -*- coding: utf-8 -*-
"""OpenRotas Desktop — AUDITORIA DE INTEGRIDADE GEOMÉTRICA (§20/§43).

Verifica DEFEITOS REAIS nas feições instaladas, camada a camada, usando os arrays espaciais do
GeoIntelligenceRepository (bbox + ponto representativo), vetorizado em numpy:

  • geometrias inválidas  — bbox com xmin>xmax ou ymin>ymax, ou coordenada não-finita (NaN/inf);
  • coordenada nula       — lon/lat ausente (NaN);
  • fora do Brasil        — ponto representativo fora da caixa nacional (inclui ilhas oceânicas) —
                            indício de erro de dado;
  • potenciais duplicatas — feições com ponto+bbox idênticos (informativo, não é falha em camadas
                            de ponto, onde repetição pode ser legítima).

Honesto quanto ao escopo: é integridade de nível BBOX/PONTO — pega inválidas/fora de área/
duplicatas. A conectividade TOPOLÓGICA completa (nós/arestas, regiões isoladas, gaps de malha)
exige construir o grafo e é um passo seguinte; aqui entregamos a checagem de integridade que os
dados permitem sem geometria pesada. Puro/defensivo: nunca levanta."""
from __future__ import annotations

import sys
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "geo"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.audit.integridade")

# Caixa nacional GENEROSA (inclui territórios oceânicos: Fernando de Noronha, Trindade, Atol das
# Rocas, São Pedro e São Paulo). Pontos fora disto são indício de erro de dado, não geografia real.
BR_LON = (-74.5, -28.0)
BR_LAT = (-34.5, 6.5)

CAMADAS = ["rodovias", "drenagem", "massas_dagua", "ferrovias", "pontes", "travessias",
           "hidrovias", "eclusas", "atracadouros_terminal", "complexos_portuarios", "sinalizacao"]

OK, PARCIAL, AUSENTE = "OK", "PARCIAL", "AUSENTE"


def _repo():
    from geo import repositorio
    return repositorio.GeoIntelligenceRepository()


def checar_camada(repo, chave: str) -> dict:
    """Defeitos de uma camada. {instalado, feicoes, invalidas, coord_nula, fora_brasil, duplicatas,
    status}. Nunca levanta."""
    res = {"chave": chave, "instalado": False, "feicoes": 0, "invalidas": 0, "coord_nula": 0,
           "fora_brasil": 0, "duplicatas": 0, "status": AUSENTE}
    a = repo.arrays(chave)
    if not a or a["n"] == 0:
        return res
    res["instalado"] = True
    res["feicoes"] = int(a["n"])
    try:
        import numpy as np
        lon, lat = a["lon"], a["lat"]
        xmin, ymin, xmax, ymax = a["xmin"], a["ymin"], a["xmax"], a["ymax"]
        nula = ~np.isfinite(lon) | ~np.isfinite(lat)
        bbox_nao_finita = ~(np.isfinite(xmin) & np.isfinite(ymin) & np.isfinite(xmax) & np.isfinite(ymax))
        bbox_invertida = (xmin > xmax) | (ymin > ymax)
        invalidas = bbox_nao_finita | bbox_invertida | nula
        dentro = (lon >= BR_LON[0]) & (lon <= BR_LON[1]) & (lat >= BR_LAT[0]) & (lat <= BR_LAT[1])
        fora = (~nula) & (~dentro)
        res["coord_nula"] = int(np.count_nonzero(nula))
        res["invalidas"] = int(np.count_nonzero(invalidas))
        res["fora_brasil"] = int(np.count_nonzero(fora))
        # potenciais duplicatas: pares idênticos (lon,lat,xmin,ymin,xmax,ymax). Vetorizado por
        # ordenação lexicográfica de uma view estruturada (barato mesmo em milhões).
        import numpy as _np
        cols = _np.stack([lon, lat, xmin, ymin, xmax, ymax], axis=1)
        finitos = _np.all(_np.isfinite(cols), axis=1)
        cf = cols[finitos]
        if cf.shape[0] > 1:
            ordem = _np.lexsort(cf.T[::-1])
            s = cf[ordem]
            iguais = _np.all(s[1:] == s[:-1], axis=1)
            res["duplicatas"] = int(_np.count_nonzero(iguais))
        res["status"] = OK if (res["invalidas"] == 0 and res["fora_brasil"] == 0) else PARCIAL
    except Exception:
        logger.warning("[INTEG] checagem de %r falhou.", chave, exc_info=True)
    return res


def auditar(camadas=None) -> dict:
    """Audita a integridade de todas as camadas. {camadas:[...], resumo:{...}}. Nunca levanta."""
    repo = _repo()
    camadas = camadas or CAMADAS
    linhas = [checar_camada(repo, c) for c in camadas]
    inst = [l for l in linhas if l["instalado"]]
    defeituosas = [l for l in inst if l["status"] != OK]
    return {"camadas": linhas,
            "resumo": {"instaladas": len(inst),
                       "limpas": sum(1 for l in inst if l["status"] == OK),
                       "com_defeito": len(defeituosas),
                       "total_invalidas": sum(l["invalidas"] for l in inst),
                       "total_fora_brasil": sum(l["fora_brasil"] for l in inst),
                       "status": OK if not defeituosas else PARCIAL}}


def render_texto(aud: dict) -> str:
    L = ["AUDITORIA DE INTEGRIDADE GEOMÉTRICA — OpenRotas", "=" * 60]
    for c in aud.get("camadas", []):
        if not c["instalado"]:
            L.append("  ○ %-24s ausente" % c["chave"])
            continue
        marca = "✓" if c["status"] == OK else "!"
        L.append("  %s %-24s %9d feições · inválidas=%d fora_BR=%d dup=%d"
                 % (marca, c["chave"], c["feicoes"], c["invalidas"], c["fora_brasil"], c["duplicatas"]))
    r = aud.get("resumo", {})
    L.append("")
    L.append("Resumo: %s/%s camadas limpas · %d inválidas · %d fora do Brasil (%s)"
             % (r.get("limpas", 0), r.get("instaladas", 0), r.get("total_invalidas", 0),
                r.get("total_fora_brasil", 0), r.get("status", "?")))
    L.append("Escopo: integridade de bbox/ponto. Conectividade topológica (nós/arestas) é passo seguinte.")
    return "\n".join(L)


def _cli(argv=None) -> int:
    aud = auditar()
    print(render_texto(aud))
    return 0 if aud["resumo"]["status"] == OK else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
