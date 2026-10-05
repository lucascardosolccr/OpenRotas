# -*- coding: utf-8 -*-
"""OpenRotas Desktop — TESTE NACIONAL DE ROTAS/COBERTURA DISTRIBUÍDA (§42/§43/§44/§45).

Não basta a malha existir no papel: ela precisa estar PRESENTE e consultável em TODAS as regiões.
Este auditor roda corredores inter-UF representativos das 5 regiões (e extremos amazônicos/
fronteira — §45) sobre o GeoIntelligenceRepository e verifica, para cada corredor, que a malha
rodoviária nacional aparece (sanidade: um corredor rodoviário de longa distância tem de cruzar a
malha) e relata os cruzamentos multimodais (rios/pontes/travessias). Assim detectamos BURACOS
REGIONAIS de dados que um teste só em SP/RJ jamais pegaria (§44).

As coordenadas são de CAPITAIS/cidades (fatos geográficos públicos), não dados fabricados — servem
apenas de pontos de corredor. A verificação é de PRESENÇA (nível bbox/corredor), honestamente
aproximada, como no restante da auditoria. Puro/defensivo: nunca levanta."""
from __future__ import annotations

import sys
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "geo"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.audit.rotas")

# Corredores inter-UF por região (origem→destino, lon/lat de capitais/cidades — fatos públicos).
# Cobrem Norte, Nordeste, Centro-Oeste, Sudeste, Sul e extremos/fronteira (§44/§45).
CORREDORES = [
    ("AC→AM  (Rio Branco→Manaus)",        (-67.81, -9.97),  (-60.02, -3.10),  "Norte"),
    ("RR→PA  (Boa Vista→Belém)",          (-60.67,  2.82),  (-48.50, -1.46),  "Norte"),
    ("AP→PA  (Macapá→Belém)",             (-51.07,  0.03),  (-48.50, -1.46),  "Norte"),
    ("RO→MT  (Porto Velho→Cuiabá)",       (-63.90, -8.76),  (-56.10, -15.60), "Norte/Centro-Oeste"),
    ("MT→MS  (Cuiabá→Campo Grande)",      (-56.10, -15.60), (-54.62, -20.47), "Centro-Oeste"),
    ("MA→RS  (São Luís→Porto Alegre)",    (-44.30, -2.53),  (-51.23, -30.03), "transversal NE→Sul"),
    ("PE→SP  (Recife→São Paulo)",         (-34.88, -8.05),  (-46.63, -23.55), "Nordeste→Sudeste"),
    ("RS→BA  (Porto Alegre→Salvador)",    (-51.23, -30.03), (-38.51, -12.97), "Sul→Nordeste"),
    ("MG→RJ  (Belo Horizonte→Rio)",       (-43.94, -19.92), (-43.20, -22.90), "Sudeste"),
    ("PR→SC  (Curitiba→Florianópolis)",   (-49.27, -25.43), (-48.55, -27.60), "Sul"),
    ("TO→GO  (Palmas→Goiânia)",           (-48.33, -10.18), (-49.25, -16.68), "transversal"),
    ("CE→PI  (Fortaleza→Teresina)",       (-38.54, -3.73),  (-42.80, -5.09),  "Nordeste"),
]


def _repo():
    from geo import repositorio
    return repositorio.GeoIntelligenceRepository()


def auditar_rotas(repo=None) -> dict:
    """Roda todos os corredores e devolve {corredores:[...], resumo:{...}}. Cada corredor tem a
    análise multimodal e um `ok` (True se a malha rodoviária aparece no corredor). Nunca levanta."""
    repo = repo or _repo()
    linhas = []
    ok_count = 0
    for rotulo, o, d, regiao in CORREDORES:
        try:
            res = repo.analise_multimodal_rota([o, d])
            rod = int(res["por_classe"].get("rodoviario", 0))
            ok = rod > 0
            linhas.append({
                "corredor": rotulo, "regiao": regiao, "ok": ok,
                "rodoviario": rod,
                "fluvial": int(res["por_classe"].get("fluvial", 0)),
                "transposicao": int(res["por_classe"].get("transposicao", 0)),
                "ferroviario": int(res["por_classe"].get("ferroviario", 0)),
                "cruza_rio": bool(res.get("cruza_rio")),
            })
            ok_count += 1 if ok else 0
        except Exception:
            logger.warning("[ROTAS] corredor %s falhou.", rotulo, exc_info=True)
            linhas.append({"corredor": rotulo, "regiao": regiao, "ok": False, "erro": True})
    total = len(CORREDORES)
    return {"corredores": linhas,
            "resumo": {"total": total, "ok": ok_count, "falhas": total - ok_count,
                       "status": "OK" if ok_count == total else "PARCIAL"}}


def render_texto(aud: dict) -> str:
    L = ["TESTE NACIONAL DE ROTAS — OpenRotas", "=" * 60]
    for c in aud.get("corredores", []):
        marca = "✓" if c.get("ok") else "✗"
        if c.get("erro"):
            L.append("  %s %-34s ERRO" % (marca, c["corredor"]))
        else:
            L.append("  %s %-34s rod=%-6d rios=%-6d transp=%-4d"
                     % (marca, c["corredor"], c["rodoviario"], c["fluvial"], c["transposicao"]))
    r = aud.get("resumo", {})
    L.append("")
    L.append("Resumo: %s/%s corredores com malha rodoviária presente (%s)"
             % (r.get("ok", 0), r.get("total", 0), r.get("status", "?")))
    L.append("Presença por corredor é nível bbox (aproximada); detecta buracos regionais de dados.")
    return "\n".join(L)


def _cli(argv=None) -> int:
    aud = auditar_rotas()
    print(render_texto(aud))
    return 0 if aud["resumo"]["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
