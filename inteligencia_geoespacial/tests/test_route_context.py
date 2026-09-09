# inteligencia_geoespacial/tests/test_route_context.py
"""Testes da Rodada 3 (integração hidrográfica) do GeoIntelligenceEngine."""
import pytest

from inteligencia_geoespacial import bases_locais as bl
from inteligencia_geoespacial import route_context as rc

DATAS_DISPONIVEIS = bool(bl.camadas_disponiveis())


# ==============================================================================
# Utilidades puras — não dependem das camadas Parquet, sempre rodam.
# ==============================================================================

def test_haversine_km_ponto_igual_e_simetrico():
    assert rc._haversine_km(-3.0, -60.0, -3.0, -60.0) == 0.0
    d1 = rc._haversine_km(-23.55, -46.63, -22.90, -43.17)
    d2 = rc._haversine_km(-22.90, -43.17, -23.55, -46.63)
    assert d1 == pytest.approx(d2, rel=1e-9)
    assert 300.0 < d1 < 400.0  # São Paulo -> Rio de Janeiro em linha reta


def test_unorm_remove_acento_e_normaliza_caixa():
    assert rc._unorm("Rio São Francisco") == "RIO SAO FRANCISCO"
    assert rc._unorm("  rio negro ") == "RIO NEGRO"
    assert rc._unorm(None) == ""


def test_pontos_amostrados_sem_geometria_interpola_reta():
    pts = rc.pontos_amostrados(0.0, 0.0, 1.0, 1.0, geometria=None, n_pontos=5)
    assert len(pts) == 5
    assert pts[0][:2] == (0.0, 0.0)
    assert pts[-1][:2] == (1.0, 1.0)
    # km acumulado é monotônico não-decrescente
    kms = [p[2] for p in pts]
    assert kms == sorted(kms)
    assert kms[0] == 0.0 and kms[-1] > 0.0


def test_pontos_amostrados_com_geometria_real_e_reutilizada():
    geometria = [(0.0, 0.0), (0.1, 0.1), (0.2, 0.2), (0.3, 0.3)]
    pts = rc.pontos_amostrados(0.0, 0.0, 0.3, 0.3, geometria=geometria, n_pontos=10)
    # geometria tem menos pontos que o pedido -> usa todos os pontos da geometria
    assert len(pts) == len(geometria)
    assert pts[0][:2] == geometria[0]
    assert pts[-1][:2] == geometria[-1]


def test_pontos_amostrados_subamostra_geometria_longa():
    geometria = [(0.0, float(i) / 100.0) for i in range(200)]
    pts = rc.pontos_amostrados(0.0, 0.0, 0.0, 1.99, geometria=geometria, n_pontos=11)
    assert len(pts) <= 11
    assert pts[0][:2] == geometria[0]
    assert pts[-1][:2] == geometria[-1]


def test_nivel_automatico():
    assert rc.nivel_automatico(50.0, suspeita=False) == 1
    assert rc.nivel_automatico(500.0, suspeita=False) == 2
    assert rc.nivel_automatico(50.0, suspeita=True) == 2
    assert rc.nivel_automatico(None, suspeita=False) == 1


def test_bacia_do_rio_conhecida_e_sem_ambiguidade():
    # Rio Solimões-Amazonas só existe registrado numa bacia (Rio Amazonas) no
    # SNIRH — caso não-ambíguo, seguro para asserção exata.
    assert rc.bacia_do_rio("Rio Solimões-Amazonas") == "RIO AMAZONAS"
    assert rc.bacia_do_rio("rio solimoes-amazonas") == "RIO AMAZONAS"  # normalização


def test_bacia_do_rio_homonimo_fica_nao_determinada():
    # "Rio Negro" existe registrado em VÁRIAS bacias distintas no SNIRH —
    # o motor nunca escolhe uma arbitrariamente (ver docstring de
    # _carregar_mapa_rio_bacia): deve devolver None, não uma bacia qualquer.
    assert rc.bacia_do_rio("Rio Negro") is None


def test_bacia_do_rio_desconhecido_e_vazio():
    assert rc.bacia_do_rio("Rio Que Nao Existe Em Nenhuma Base 123") is None
    assert rc.bacia_do_rio("") is None
    assert rc.bacia_do_rio(None) is None


def test_analisar_rota_coordenadas_invalidas_fail_open():
    ctx = rc.analisar_rota(origem=("x", "y"), destino=(1.0, 2.0))
    assert isinstance(ctx, rc.ContextoGeograficoRota)
    assert ctx.avisos and "inválidas" in ctx.avisos[0]
    assert ctx.rios_detectados == [] and ctx.corpos_dagua == []


def test_analisar_rota_sem_geometria_gera_aviso_de_estimativa():
    ctx = rc.analisar_rota(origem=(0.0, 0.0), destino=(0.0, 1.0), raio_km=0.001, nivel=1)
    assert any("corda geodésica" in a for a in ctx.avisos)


def test_geo_intelligence_repository_cache_hit_evita_reconsulta(monkeypatch):
    chamadas = {"n": 0}

    def _fake_mais_proximos(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        chamadas["n"] += 1
        return [{"nome": "Rio Fake", "distancia_km": 1.23, "navegavel": "Sim", "regime": "Perene"}]

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake_mais_proximos)
    repo = rc.GeoIntelligenceRepository()
    r1 = repo.consultar("drenagem", -3.11901234, -60.02171234, raio_km=5.0)
    r2 = repo.consultar("drenagem", -3.11901111, -60.02171111, raio_km=5.0)  # arredonda igual
    assert chamadas["n"] == 1  # segunda chamada veio do cache
    assert r1 == r2 == [{"nome": "Rio Fake", "distancia_km": 1.23, "navegavel": "Sim", "regime": "Perene"}]
    assert repo.tamanho() == 1
    repo.limpar()
    assert repo.tamanho() == 0


def test_geo_intelligence_repository_fail_open(monkeypatch):
    def _explode(*a, **k):
        raise RuntimeError("camada indisponível")

    monkeypatch.setattr(rc._bl, "mais_proximos", _explode)
    repo = rc.GeoIntelligenceRepository()
    assert repo.consultar("drenagem", -3.0, -60.0, raio_km=5.0) == []


# ==============================================================================
# Fim-a-fim com dados reais (mesmo ponto de referência já usado e validado em
# test_validators.py::test_rio_mais_proximo_nomeado_manaus — reaproveita o
# mesmo raio para permanecer consistente com um resultado já comprovado).
# ==============================================================================

pytestmark_dados = pytest.mark.skipif(
    not DATAS_DISPONIVEIS,
    reason="Camadas derivadas ausentes. Gere com construir_bases_locais_ibge.py",
)


@pytestmark_dados
def test_analisar_rota_detecta_hidrografia_real_em_manaus():
    origem = destino = (-3.1190, -60.0217)
    ctx = rc.analisar_rota(origem, destino, raio_km=50.0, nivel=1)
    assert isinstance(ctx, rc.ContextoGeograficoRota)
    assert ctx.rios_detectados or ctx.corpos_dagua
    for r in ctx.rios_detectados:
        assert r.nome and r.nome.strip()
        assert r.fonte == "IBGE BC250/BC100 (drenagem)"
    assert ctx.confianca_geral > 0
    assert ctx.confianca_nivel in ("alta", "media")


@pytestmark_dados
def test_analisar_rota_fora_do_brasil_nao_encontra_nada_e_avisa():
    ctx = rc.analisar_rota(origem=(0.0, -30.0), destino=(0.1, -30.1), raio_km=5.0, nivel=1)
    assert ctx.rios_detectados == [] and ctx.corpos_dagua == []
    assert any("Nenhum cruzamento hidrográfico" in a for a in ctx.avisos)
    assert ctx.confianca_geral == 0


@pytestmark_dados
def test_analisar_rota_usa_repositorio_compartilhado_por_padrao():
    repo_antes = rc.repositorio_padrao()
    rc.analisar_rota((-3.1190, -60.0217), (-3.1190, -60.0217), raio_km=50.0, nivel=1)
    assert rc.repositorio_padrao() is repo_antes  # mesma instância, cache reaproveitado
    assert repo_antes.tamanho() > 0
