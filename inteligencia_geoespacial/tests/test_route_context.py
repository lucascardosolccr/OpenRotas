# inteligencia_geoespacial/tests/test_route_context.py
"""Testes das Rodadas 3-5 (hidrografia, aquaviário, pontes) do GeoIntelligenceEngine."""
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
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake_mais_proximos)
    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _fake_mais_proximos)
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
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _explode)
    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _explode)
    repo = rc.GeoIntelligenceRepository()
    assert repo.consultar("drenagem", -3.0, -60.0, raio_km=5.0) == []


# ==============================================================================
# Rodada 4 — integração aquaviária (travessias/hidrovias/portos, índice de
# dependência aquaviária, alternativa sem balsa). Utilidades puras.
# ==============================================================================

def test_montar_alternativa_sem_balsa_travessia_ainda_vence():
    alt = rc.montar_alternativa_sem_balsa(50.0, 90.0)
    assert isinstance(alt, rc.AlternativaRodoviaria)
    assert alt.diferenca_km == 40.0
    assert alt.diferenca_pct == 80.0
    assert "travessia continua sendo a rota mais curta" in alt.conclusao


def test_montar_alternativa_sem_balsa_diferenca_pequena_recomenda_trocar():
    alt = rc.montar_alternativa_sem_balsa(100.0, 103.0)
    assert alt.diferenca_pct == 3.0
    assert "considerar preferi-la" in alt.conclusao


def test_montar_alternativa_sem_balsa_alternativa_mais_curta():
    alt = rc.montar_alternativa_sem_balsa(100.0, 95.0)
    assert alt.diferenca_km == -5.0
    assert "não há motivo geográfico" in alt.conclusao


def test_montar_alternativa_sem_balsa_entradas_invalidas_fail_open():
    assert rc.montar_alternativa_sem_balsa(None, 90.0) is None
    assert rc.montar_alternativa_sem_balsa(50.0, "x") is None
    assert rc.montar_alternativa_sem_balsa(0.0, 90.0) is None
    assert rc.montar_alternativa_sem_balsa(50.0, -1.0) is None


def test_indice_dependencia_aquaviaria_sem_evidencia_e_zero():
    assert rc._indice_dependencia_aquaviaria([], [], [], []) == 0


def test_indice_dependencia_aquaviaria_travessia_pesa_mais():
    travessia = rc.Feicao(nome="X", tipo="travessia (balsa)", distancia_eixo_km=1.0,
                          km_desde_origem=0.0, fonte="teste")
    porto = rc.Feicao(nome="Y", tipo="complexo portuário", distancia_eixo_km=2.0,
                      km_desde_origem=0.0, fonte="teste")
    so_porto = rc._indice_dependencia_aquaviaria([], [], [], [porto])
    com_travessia = rc._indice_dependencia_aquaviaria([], [travessia], [], [porto])
    assert com_travessia > so_porto
    assert com_travessia <= 100


def test_detectar_feicoes_nome_ausente_vira_rotulo_explicito(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": None, "distancia_km": 3.0}]

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    achados = rc._detectar_feicoes([(0.0, 0.0, 0.0)], repo, "eclusas", 10.0, "eclusa", "fonte-teste")
    assert len(achados) == 1
    assert achados[0].nome == "<eclusa sem nome>"


def test_detectar_feicoes_propaga_coordenada_real(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Porto X", "distancia_km": 1.0, "lat": -22.5, "lon": -43.2}]

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    achados = rc._detectar_feicoes([(0.0, 0.0, 0.0)], repo, "complexos_portuarios", 10.0, "porto", "fonte-teste")
    assert achados[0].lat == -22.5 and achados[0].lon == -43.2


def test_detectar_feicoes_sem_coordenada_na_base_fica_none(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Porto Y", "distancia_km": 1.0}]  # sem 'lat'/'lon' na resposta

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    achados = rc._detectar_feicoes([(0.0, 0.0, 0.0)], repo, "complexos_portuarios", 10.0, "porto", "fonte-teste")
    assert achados[0].lat is None and achados[0].lon is None


def test_detectar_pontes_propaga_coordenada_propria_da_ponte(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Ponte Z", "distancia_km": 0.2, "lat": -10.1, "lon": -50.2}]

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    cz = _cruzamento(nome="Rio W", lat=-10.1001, lon=-50.2001)
    pontes = rc._detectar_pontes_nos_cruzamentos([cz], repo)
    assert pontes[0].lat == -10.1 and pontes[0].lon == -50.2  # coordenada da PONTE, não do cruzamento


def test_detectar_feicoes_deduplica_mantendo_menor_distancia(monkeypatch):
    respostas = [
        [{"nome": "Porto X", "distancia_km": 5.0}],
        [{"nome": "Porto X", "distancia_km": 2.0}],  # mesmo nome, mais perto no 2º ponto amostrado
    ]

    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return respostas.pop(0)

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    achados = rc._detectar_feicoes(
        [(0.0, 0.0, 0.0), (0.0, 0.1, 10.0)], repo, "complexos_portuarios", 10.0,
        "complexo portuário", "fonte-teste")
    assert len(achados) == 1
    assert achados[0].distancia_eixo_km == 2.0


# ==============================================================================
# Rodada 5 — pontes NO cruzamento hidrográfico (§8 da missão). Utilidades puras.
# ==============================================================================

def _cruzamento(nome="Rio Fake", lat=0.0, lon=0.0, km=0.0):
    return rc.CruzamentoHidrografico(
        nome=nome, camada="drenagem", distancia_eixo_km=1.0, km_desde_origem=km,
        km_ate_destino=None, navegavel=None, regime=None, bacia=None,
        fonte="teste", confianca="alta", lat=lat, lon=lon)


def test_detectar_pontes_ignora_cruzamento_sem_coordenada(monkeypatch):
    chamado = {"n": 0}

    def _fake(*a, **k):
        chamado["n"] += 1
        return []

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    cz = rc.CruzamentoHidrografico(nome="Sem coordenada", camada="drenagem",
                                    distancia_eixo_km=1.0, km_desde_origem=0.0,
                                    km_ate_destino=None, navegavel=None, regime=None,
                                    bacia=None, fonte="teste", confianca="alta",
                                    lat=None, lon=None)
    assert rc._detectar_pontes_nos_cruzamentos([cz], repo) == []
    assert chamado["n"] == 0  # nunca consulta sem coordenada


def test_detectar_pontes_sem_nome_usa_rotulo_derivado_do_rio(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": None, "distancia_km": 0.4}]

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    cz = _cruzamento(nome="Rio Fake")
    pontes = rc._detectar_pontes_nos_cruzamentos([cz], repo)
    assert len(pontes) == 1
    assert pontes[0].nome == "Ponte sobre Rio Fake"  # nunca inventa um nome próprio
    assert pontes[0].tipo == "ponte"


def test_detectar_pontes_com_nome_cadastrado_usa_o_nome_real(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Ponte Real do Cadastro", "distancia_km": 0.1}]

    monkeypatch.setattr(rc._bl, "mais_proximos", _fake)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    pontes = rc._detectar_pontes_nos_cruzamentos([_cruzamento()], repo)
    assert pontes[0].nome == "Ponte Real do Cadastro"


def test_detectar_pontes_nenhuma_encontrada_no_raio(monkeypatch):
    monkeypatch.setattr(rc._bl, "mais_proximos", lambda *a, **k: [])
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", lambda *a, **k: [])
    repo = rc.GeoIntelligenceRepository()
    assert rc._detectar_pontes_nos_cruzamentos([_cruzamento()], repo) == []


def test_detectar_pontes_fail_open(monkeypatch):
    def _explode(*a, **k):
        raise RuntimeError("camada indisponível")

    monkeypatch.setattr(rc._bl, "mais_proximos", _explode)
    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _explode)
    repo = rc.GeoIntelligenceRepository()
    assert rc._detectar_pontes_nos_cruzamentos([_cruzamento()], repo) == []


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


# ==============================================================================
# Rodada 5 fim-a-fim: Ponte Rio-Niterói sobre a Baía de Guanabara/Canal do
# Mangue — uma das pontes mais conhecidas do Brasil, boa prova de que a
# associação cruzamento->ponte encontra dado real no ponto certo.
# ==============================================================================

@pytestmark_dados
def test_analisar_rota_detecta_ponte_rio_niteroi_no_cruzamento():
    # Coordenada da própria ponte (confirmada previamente contra
    # bases_locais.mais_proximos('pontes', ...)) — origem=destino faz o
    # corredor amostrado ficar exatamente sobre o cruzamento.
    origem = destino = (-22.8702, -43.1642)
    ctx = rc.analisar_rota(origem, destino, raio_km=5.0, nivel=1)
    assert ctx.rios_detectados or ctx.corpos_dagua  # há cruzamento hidrográfico aqui
    nomes_pontes = [p.nome for p in ctx.pontes]
    assert any("Rio-Niterói" in n for n in nomes_pontes)
    ponte = next(p for p in ctx.pontes if "Rio-Niterói" in p.nome)
    assert ponte.tipo == "ponte"
    assert ponte.distancia_eixo_km is not None and ponte.distancia_eixo_km <= 1.0
    assert any("confirmado(s) por ponte" in parte for parte in [ctx.motivo_decisao])


# ==============================================================================
# Rodada 4 fim-a-fim: travessia real da BR-174 sobre o Rio Negro (Manaus) e o
# Porto de Manaus — infraestrutura pública conhecida, boa prova de que a
# detecção aquaviária por geometria encontra dado real, não um artefato.
# ==============================================================================

@pytestmark_dados
def test_analisar_rota_detecta_travessia_real_br174_manaus():
    origem = destino = (-3.1190, -60.0217)
    ctx = rc.analisar_rota(origem, destino, raio_km=50.0, nivel=1)
    nomes_travessias = [t.nome for t in ctx.travessias]
    assert any("BR-174" in n for n in nomes_travessias)
    for t in ctx.travessias:
        assert t.tipo == "travessia (balsa)"
        assert t.fonte == "IBGE BC250/BC100 (travessias)"
    assert ctx.dependencia_aquaviaria is not None and ctx.dependencia_aquaviaria >= 50
    assert ctx.nivel_analise >= 3


@pytestmark_dados
def test_analisar_rota_detecta_porto_de_manaus():
    origem = destino = (-3.1190, -60.0217)
    ctx = rc.analisar_rota(origem, destino, raio_km=50.0, nivel=1)
    nomes_portos = [p.nome for p in ctx.portos_terminais]
    assert "Porto de Manaus" in nomes_portos


@pytestmark_dados
def test_analisar_rota_raio_explicito_e_sempre_respeitado_na_fase_aquaviaria():
    # Regressão do bug corrigido: um raio_km explícito não pode ser
    # substituído silenciosamente por um raio menor do nível automático.
    origem = destino = (-3.1190, -60.0217)
    ctx_raio_curto = rc.analisar_rota(origem, destino, raio_km=1.0, nivel=1)
    ctx_raio_largo = rc.analisar_rota(origem, destino, raio_km=50.0, nivel=1)
    assert len(ctx_raio_largo.travessias) >= len(ctx_raio_curto.travessias)
    assert len(ctx_raio_largo.portos_terminais) >= len(ctx_raio_curto.portos_terminais)


# ==============================================================================
# Rodada 14 — caminho rápido em memória para as camadas pequenas (Performance).
# ==============================================================================

def test_camadas_pequenas_sao_exatamente_as_seis_camadas_leves():
    # Nunca inclui `drenagem`/`massas_dagua` (pesadas demais para memória).
    assert set(rc._CAMADAS_PEQUENAS) == {
        "pontes", "travessias", "hidrovias", "eclusas",
        "atracadouros_terminal", "complexos_portuarios",
    }
    assert "drenagem" not in rc._CAMADAS_PEQUENAS
    assert "massas_dagua" not in rc._CAMADAS_PEQUENAS


@pytestmark_dados
@pytest.mark.parametrize("camada", rc._CAMADAS_PEQUENAS)
def test_caminho_rapido_bate_com_mais_proximos_para_cada_camada_pequena(camada):
    # Mesmo resultado (mesma ordem, mesma distância) que a leitura em disco —
    # só a fonte dos dados muda, nunca o critério de busca/ranking.
    lon, lat, raio = -60.0217, -3.1190, 60.0
    esperado = bl.mais_proximos(camada, lon, lat, raio_km=raio, limite=10)
    obtido = rc._consultar_rapido_camada_pequena(camada, lon, lat, raio_km=raio, limite=10)
    assert len(obtido) == len(esperado)
    for e, o in zip(esperado, obtido):
        assert o["nome"] == e["nome"]
        assert abs(o["distancia_km"] - e["distancia_km"]) < 1e-6


@pytestmark_dados
def test_repositorio_usa_caminho_rapido_para_camada_pequena_sem_tocar_disco(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("não deveria reler o Parquet do disco para camada pequena")

    monkeypatch.setattr(rc._bl, "mais_proximos", _explode)
    repo = rc.GeoIntelligenceRepository()
    resultado = repo.consultar("pontes", -3.1190, -60.0217, raio_km=60.0, limite=10)
    assert isinstance(resultado, list)


@pytestmark_dados
def test_repositorio_continua_usando_disco_para_camada_pesada(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("camada pesada não deveria usar o caminho rápido em memória")

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _explode)
    repo = rc.GeoIntelligenceRepository()
    resultado = repo.consultar("drenagem", -3.1190, -60.0217, raio_km=5.0, limite=5)
    assert isinstance(resultado, list)


# ==============================================================================
# Rodada 14 — cache de "janela ampla" das camadas pesadas (drenagem/massas_dagua).
# ==============================================================================

@pytestmark_dados
@pytest.mark.parametrize("camada,lon,lat,raio", [
    ("drenagem", -60.0217, -3.1190, 5.0),
    ("drenagem", -60.0217, -3.1190, 12.0),
    ("drenagem", -43.10, -22.895, 12.0),
    ("massas_dagua", -60.55, -3.35, 60.0),  # raio explícito acima da janela padrão
])
def test_cache_camada_pesada_bate_com_mais_proximos(camada, lon, lat, raio):
    # Mesmo resultado que a leitura direta em disco — a janela cacheada
    # nunca pode truncar um raio pedido, nem para raios maiores que a
    # janela padrão (12 km) da escalada automática.
    rc._limpar_cache_camadas_pesadas()
    esperado = bl.mais_proximos(camada, lon, lat, raio_km=raio, limite=10)
    obtido = rc._consultar_camada_pesada_cacheada(camada, lon, lat, raio_km=raio, limite=10)
    assert len(obtido) == len(esperado)
    for e, o in zip(esperado, obtido):
        assert o["nome"] == e["nome"]
        assert abs(o["distancia_km"] - e["distancia_km"]) < 1e-6


@pytestmark_dados
def test_cache_camada_pesada_reaproveita_janela_entre_raios_crescentes():
    # Padrão real da escalada automática de nível (§32): mesmo ponto,
    # raios crescentes — não pode gerar uma nova leitura de disco a cada
    # nível quando a janela já cacheada cobre o raio pedido.
    rc._limpar_cache_camadas_pesadas()
    lon, lat = -60.0217, -3.1190
    rc._consultar_camada_pesada_cacheada("drenagem", lon, lat, raio_km=5.0, limite=10)
    assert len(rc._cache_janela_pesada) == 1
    rc._consultar_camada_pesada_cacheada("drenagem", lon, lat, raio_km=6.0, limite=10)
    rc._consultar_camada_pesada_cacheada("drenagem", lon, lat, raio_km=8.0, limite=10)
    rc._consultar_camada_pesada_cacheada("drenagem", lon, lat, raio_km=12.0, limite=10)
    assert len(rc._cache_janela_pesada) == 1  # uma única leitura de disco serviu os 4 raios


@pytestmark_dados
def test_cache_camada_pesada_nao_serve_do_cache_quando_raio_pedido_excede_a_janela(monkeypatch):
    chamadas = {"n": 0}
    original = rc._bl._busca_com_filtro

    def _contando(*a, **k):
        chamadas["n"] += 1
        return original(*a, **k)

    rc._limpar_cache_camadas_pesadas()
    monkeypatch.setattr(rc._bl, "_busca_com_filtro", _contando)
    rc._consultar_camada_pesada_cacheada("drenagem", -60.0217, -3.1190, raio_km=5.0, limite=10)
    assert chamadas["n"] == 1
    # Raio muito maior que a janela cacheada -> tem que reler o disco (nunca trunca silenciosamente)
    rc._consultar_camada_pesada_cacheada("drenagem", -60.0217, -3.1190, raio_km=100.0, limite=10)
    assert chamadas["n"] == 2


def test_limpar_cache_camadas_pesadas_esvazia_o_cache():
    rc._cache_janela_pesada[("drenagem", -3.1, -60.0)] = (12.0, None)
    assert len(rc._cache_janela_pesada) >= 1
    rc._limpar_cache_camadas_pesadas()
    assert len(rc._cache_janela_pesada) == 0


def test_cache_camada_pesada_respeita_orcamento_de_memoria_via_limite_de_entradas(monkeypatch):
    # Orçamento de memória em produção (§ comentário no módulo): mesmo com
    # muitos pontos distintos consultados de verdade (via
    # _consultar_camada_pesada_cacheada, não manipulando o dict direto), o
    # cache nunca cresce acima de `_CACHE_PESADAS_MAX_ENTRADAS` — o LRU
    # descarta a entrada menos recentemente usada.
    import pandas as pd

    vazio = pd.DataFrame(columns=["geometry_wkb", "lon", "lat", "xmin", "ymin",
                                   "xmax", "ymax", "tipo_geom", "nome",
                                   "fonte_base", "fonte_uf"])
    monkeypatch.setattr(rc._bl, "_busca_com_filtro", lambda *a, **k: vazio)

    rc._limpar_cache_camadas_pesadas()
    for i in range(rc._CACHE_PESADAS_MAX_ENTRADAS + 50):
        rc._consultar_camada_pesada_cacheada("drenagem", -60.0, -3.0 - i * 0.2, raio_km=5.0, limite=5)
    assert len(rc._cache_janela_pesada) == rc._CACHE_PESADAS_MAX_ENTRADAS
