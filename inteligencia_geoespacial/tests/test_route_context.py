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


# ==============================================================================
# [CRUZAMENTO-REAL - 459ª] Teste geométrico de cruzamento real (puro, sem Parquet).
# ==============================================================================

def _wkb_line(pts):
    import struct
    b = b"\x01" + struct.pack("<I", 2) + struct.pack("<I", len(pts))
    for x, y in pts:
        b += struct.pack("<dd", x, y)
    return b


def _wkb_poly(ring):
    import struct
    b = b"\x01" + struct.pack("<I", 3) + struct.pack("<I", 1) + struct.pack("<I", len(ring))
    for x, y in ring:
        b += struct.pack("<dd", x, y)
    return b


def test_segmentos_cruzam():
    assert rc._segmentos_cruzam((0, 0), (2, 2), (0, 2), (2, 0)) is True   # X
    assert rc._segmentos_cruzam((0, 0), (1, 0), (0, 1), (1, 1)) is False  # paralelos
    assert rc._segmentos_cruzam((0, 0), (2, 0), (1, 0), (1, 1)) is True   # toque em T


def test_linha_cruza_linestring_rio():
    rio = _wkb_line([(0.5, 0.0), (0.5, 1.0)])            # rio vertical em lon=0.5
    assert rc._linha_cruza_geometria([(0.0, 0.5), (1.0, 0.5)], rio) is True    # rota cruza
    assert rc._linha_cruza_geometria([(0.9, 0.0), (0.9, 1.0)], rio) is False   # rota paralela (margeia)


def test_linha_cruza_polygon_massa_dagua():
    lago = _wkb_poly([(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6), (0.4, 0.4)])
    assert rc._linha_cruza_geometria([(0.0, 0.5), (1.0, 0.5)], lago) is True   # atravessa o lago
    assert rc._linha_cruza_geometria([(0.0, 0.9), (1.0, 0.9)], lago) is False  # passa longe


def test_linha_cruza_defensivo():
    rio = _wkb_line([(0.5, 0.0), (0.5, 1.0)])
    assert rc._linha_cruza_geometria([], rio) is None                # sem rota
    assert rc._linha_cruza_geometria([(0, 0), (1, 1)], None) is None  # sem geometria
    import struct
    ponto = b"\x01" + struct.pack("<I", 1) + struct.pack("<dd", 0.5, 0.5)
    assert rc._linha_cruza_geometria([(0, 0), (1, 1)], ponto) is None  # ponto não é "atravessado"


def test_ranquear_por_distancia_alcanca_linha_longa():
    # [HIDROVIA-LONGA - 460ª] feição-LINHA longa cujo PONTO REPRESENTATIVO cai longe do ponto consultado,
    # mas cujo TRAÇADO passa a ~1 km: o pré-filtro por bbox (limite inferior) tem de mantê-la — antes o
    # filtro pelo ponto representativo a descartava. Puro (DataFrame sintético, sem Parquet).
    import pandas as pd
    rio = _wkb_line([(0.01, -5.0), (0.01, 0.0), (0.01, 5.0)])   # rio vertical passando ~1 km do ponto (0,0)
    df = pd.DataFrame([{
        "geometry_wkb": rio, "lon": 0.01, "lat": 5.0,            # ponto representativo ~550 km ao norte
        "xmin": 0.0, "ymin": -5.0, "xmax": 0.02, "ymax": 5.0,    # bbox cobre a latitude consultada
        "tipo_geom": "LINHA", "nome": "Rio Longo", "fonte_base": "BC250", "fonte_uf": "BR"}])
    achados = bl._ranquear_por_distancia(df, 0.0, 0.0, raio_km=10.0, limite=5)
    assert len(achados) == 1 and achados[0]["nome"] == "Rio Longo"
    assert achados[0]["distancia_km"] < 3.0                      # distância REAL ao traçado (~1,1 km)
    # controle: uma linha realmente distante (bbox longe) continua fora do raio
    rio2 = _wkb_line([(3.0, 3.0), (3.0, 4.0)])
    df2 = pd.DataFrame([{
        "geometry_wkb": rio2, "lon": 3.0, "lat": 4.0,
        "xmin": 3.0, "ymin": 3.0, "xmax": 3.0, "ymax": 4.0,
        "tipo_geom": "LINHA", "nome": "Rio Distante", "fonte_base": "BC250", "fonte_uf": "BR"}])
    assert bl._ranquear_por_distancia(df2, 0.0, 0.0, 10.0, 5) == []
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
    assert isinstance(pontes[0], rc.Ponte)


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
        assert r.fonte == "IBGE BC250 (drenagem)"
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
    assert isinstance(ponte, rc.Ponte)
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
        assert t.fonte == "IBGE BC250 (travessias)"
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

def test_camadas_pequenas_sao_exatamente_as_sete_camadas_leves():
    # Nunca inclui `drenagem`/`massas_dagua`/`rodovias` (pesadas demais para
    # memória — `rodovias` usa o cache de janela ampla, ver Rodada 3/Missão 2).
    assert set(rc._CAMADAS_PEQUENAS) == {
        "pontes", "travessias", "hidrovias", "eclusas",
        "atracadouros_terminal", "complexos_portuarios", "ferrovias",
    }
    assert "drenagem" not in rc._CAMADAS_PEQUENAS
    assert "massas_dagua" not in rc._CAMADAS_PEQUENAS
    assert "rodovias" not in rc._CAMADAS_PEQUENAS


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


# ==============================================================================
# Missão 2 / Rodada 3 — integração rodoviária (rodovias oficiais BR/UF
# identificadas ao longo da rota, camada `rodovias` do BC250/BC100).
# ==============================================================================

def test_detectar_rodovias_descarta_trechos_sem_sigla(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"sigla": None, "distancia_km": 0.2}, {"sigla": "", "distancia_km": 0.1}]

    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _fake)
    repo = rc.GeoIntelligenceRepository()
    rodovias = rc._detectar_rodovias([(0.0, 0.0, 0.0)], repo, 10.0)
    assert rodovias == []  # sem sigla -> não fabrica "rodovia sem nome"


def test_detectar_rodovias_dedup_mantem_menor_distancia(monkeypatch):
    respostas = [
        [{"sigla": "BR-364", "distancia_km": 5.0, "jurisdicao": "Federal"}],
        [{"sigla": "br-364", "distancia_km": 1.2, "jurisdicao": "Federal"}],  # mesma rodovia, caixa diferente
    ]

    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return respostas.pop(0)

    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _fake)
    repo = rc.GeoIntelligenceRepository()
    rodovias = rc._detectar_rodovias(
        [(0.0, 0.0, 0.0), (0.0, 0.1, 10.0)], repo, 10.0)
    assert len(rodovias) == 1
    assert rodovias[0].distancia_eixo_km == 1.2


def test_detectar_rodovias_extrai_atributos_reais_sem_inventar(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{
            "sigla": "BR-101", "distancia_km": 0.5, "jurisdicao": "Federal",
            "administra": "Concessionada", "concession": "CCR RioSP",
            "revestimen": "Pavimentado", "tipopavime": "Asfalto",
            "nrpistas": 2.0, "nrfaixas": 4.0, "limitevelo": None,
            "lat": -22.9, "lon": -43.1,
        }]

    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _fake)
    repo = rc.GeoIntelligenceRepository()
    rodovias = rc._detectar_rodovias([(0.0, 0.0, 0.0)], repo, 10.0)
    assert len(rodovias) == 1
    r = rodovias[0]
    assert r.sigla == "BR-101"
    assert r.jurisdicao == "Federal"
    assert r.concessionaria == "CCR RioSP"
    assert r.nr_pistas == 2 and r.nr_faixas == 4
    assert r.limite_velocidade_kmh is None  # nunca inventa quando a base não tem
    assert r.lat == -22.9 and r.lon == -43.1


def test_detectar_rodovias_extrai_trafego_e_situacao_fisica_sem_inventar(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"sigla": "BR-101", "distancia_km": 0.5, "trafego": "Permanente",
                  "situacaofi": "Construída"}]

    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _fake)
    repo = rc.GeoIntelligenceRepository()
    r = rc._detectar_rodovias([(0.0, 0.0, 0.0)], repo, 10.0)[0]
    assert r.trafego == "Permanente"
    assert r.situacao_fisica == "Construída"


def test_detectar_rodovias_sem_trafego_nem_situacao_fica_none(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"sigla": "BR-101", "distancia_km": 0.5}]

    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _fake)
    repo = rc.GeoIntelligenceRepository()
    r = rc._detectar_rodovias([(0.0, 0.0, 0.0)], repo, 10.0)[0]
    assert r.trafego is None
    assert r.situacao_fisica is None


def test_detectar_rodovias_concessao_nao_vira_none_nao_string_literal():
    # A base grava "Não" quando não há concessão — isso vira None (ausência
    # real), não uma string "Não" solta, para não confundir "tem concessão
    # chamada Não" com "não tem concessão".
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"sigla": "MT-170", "distancia_km": 0.3, "concession": "Não"}]

    import inteligencia_geoespacial.route_context as rc_mod
    orig = rc_mod._consultar_camada_pesada_cacheada
    rc_mod._consultar_camada_pesada_cacheada = _fake
    try:
        repo = rc.GeoIntelligenceRepository()
        rodovias = rc._detectar_rodovias([(0.0, 0.0, 0.0)], repo, 10.0)
        assert rodovias[0].concessionaria is None
    finally:
        rc_mod._consultar_camada_pesada_cacheada = orig


def test_rodovias_esta_no_cache_de_janela_ampla():
    assert "rodovias" in rc._CAMADAS_COM_CACHE_AMPLO


@pytestmark_dados
def test_analisar_rota_identifica_br116_entre_sp_e_rj():
    # BR-116 (Via Dutra/Rio-Santos) é a ligação rodoviária federal conhecida
    # entre São Paulo e Rio de Janeiro — boa prova de que a detecção usa
    # dado real, não um artefato de teste.
    origem, destino = (-23.55, -46.63), (-22.90, -43.20)
    ctx = rc.analisar_rota(origem, destino, distancia_km=430.0, raio_km=10.0)
    siglas = [r.sigla for r in ctx.rodovias]
    assert any("BR-116" in s for s in siglas)
    for r in ctx.rodovias:
        assert r.fonte == "IBGE BC250 (rodovias)"
    assert any("Rodovia" in m for m in [ctx.motivo_decisao])


@pytestmark_dados
def test_analisar_rota_sem_rodovia_gera_aviso_honesto():
    # Ponto isolado sem nenhuma rodovia com sigla oficial por perto (raio
    # bem estreito) -> aviso explícito, nunca lista vazia silenciosa.
    origem = destino = (-3.1190, -60.0217)
    ctx = rc.analisar_rota(origem, destino, distancia_km=0.0, raio_km=0.05)
    if not ctx.rodovias:
        assert any("rodovia" in a.lower() for a in ctx.avisos)


# ==============================================================================
# Missão 2 / Rodada 4 — integração ferroviária (trechos ferroviários
# próximos à rota, camada `ferrovias` do BC250/BC100).
# ==============================================================================

def test_ferrovias_esta_no_caminho_rapido_camadas_pequenas():
    assert "ferrovias" in rc._CAMADAS_PEQUENAS
    assert "ferrovias" not in rc._CAMADAS_COM_CACHE_AMPLO


def test_detectar_ferrovias_usa_codigo_do_trecho_quando_sem_nome(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": None, "codtrechof": "EF-462", "distancia_km": 1.5}]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    ferrovias = rc._detectar_ferrovias([(0.0, 0.0, 0.0)], repo, 10.0)
    assert len(ferrovias) == 1
    assert ferrovias[0].nome == "EF-462"  # nunca inventa nome próprio, usa o código real


def test_detectar_ferrovias_sem_nome_nem_codigo_usa_rotulo_explicito(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": None, "codtrechof": None, "distancia_km": 0.8}]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    ferrovias = rc._detectar_ferrovias([(0.0, 0.0, 0.0)], repo, 10.0)
    assert ferrovias[0].nome == "<ferrovia sem nome>"


def test_detectar_ferrovias_dedup_mantem_menor_distancia(monkeypatch):
    respostas = [
        [{"nome": "Estrada de Ferro X", "distancia_km": 5.0}],
        [{"nome": "estrada de ferro x", "distancia_km": 1.1}],
    ]

    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return respostas.pop(0)

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    ferrovias = rc._detectar_ferrovias(
        [(0.0, 0.0, 0.0), (0.0, 0.1, 10.0)], repo, 10.0)
    assert len(ferrovias) == 1
    assert ferrovias[0].distancia_eixo_km == 1.1


def test_detectar_ferrovias_extrai_atributos_reais_sem_inventar(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{
            "nome": "Estrada de Ferro Vitória a Minas", "distancia_km": 2.0,
            "tipotrecho": "Trecho para trem", "bitola": "Métrica",
            "eletrifica": "Não", "nrlinhas": "Simples",
            "jurisdicao": "Federal", "administra": "Concessionada",
            "concession": "Vale", "lat": -19.9, "lon": -43.1,
        }]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    ferrovias = rc._detectar_ferrovias([(0.0, 0.0, 0.0)], repo, 10.0)
    f = ferrovias[0]
    assert f.nome == "Estrada de Ferro Vitória a Minas"
    assert f.bitola == "Métrica"
    assert f.eletrificada == "Não"
    assert f.concessionaria == "Vale"
    assert f.lat == -19.9 and f.lon == -43.1


def test_detectar_ferrovias_extrai_posicao_relativa_e_situacao_fisica(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Linha X", "distancia_km": 1.0, "posicaorel": "Subterrânea",
                  "situacaofi": "Abandonada"}]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    f = rc._detectar_ferrovias([(0.0, 0.0, 0.0)], repo, 10.0)[0]
    assert f.posicao_relativa == "Subterrânea"
    assert f.situacao_fisica == "Abandonada"


def test_detectar_ferrovias_sem_posicao_nem_situacao_fica_none(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Linha X", "distancia_km": 1.0}]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    f = rc._detectar_ferrovias([(0.0, 0.0, 0.0)], repo, 10.0)[0]
    assert f.posicao_relativa is None
    assert f.situacao_fisica is None


@pytestmark_dados
def test_analisar_rota_identifica_estrada_de_ferro_vitoria_a_minas():
    # EFVM é uma ferrovia real e conhecida entre Minas Gerais e o Espírito
    # Santo — boa prova de dado real, não artefato de teste.
    origem, destino = (-19.55, -40.30), (-19.95, -40.30)
    ctx = rc.analisar_rota(origem, destino, distancia_km=45.0, raio_km=8.0)
    nomes = [f.nome for f in ctx.ferrovias]
    assert any("Vitória" in n or "Vitoria" in n for n in nomes)
    # [HIDROVIA-LONGA - 460ª] O pré-filtro por BBOX (limite inferior) passou a alcançar também as linhas
    # NACIONAIS (BC250) da EFVM, cujo ponto REPRESENTATIVO caía longe do eixo e antes era descartado — a
    # detecção ficou mais completa (recall). Ambas as fontes são reais; a extração regional (BC100-ES)
    # continua presente. Não se exige mais que TODAS sejam BC100-ES (isso codificava o bug do pré-filtro).
    fontes = {f.fonte for f in ctx.ferrovias}
    assert "IBGE BC100 (ferrovias) — ES" in fontes


# ==============================================================================
# Missão 2 / Rodada 5 — enriquecimento de atributos já coletados mas não
# usados (pontes, massas d'água/drenagem, complexos portuários).
# ==============================================================================

def test_detectar_pontes_extrai_atributos_reais(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{
            "nome": "Ponte Teste", "distancia_km": 0.3,
            "tipoponte": "Estaiada", "tipopavime": "Asfalto",
            "extensao": 850.0, "largura": 12.0,
        }]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    pontes = rc._detectar_pontes_nos_cruzamentos([_cruzamento()], repo)
    p = pontes[0]
    assert p.tipo_ponte == "Estaiada"
    assert p.tipo_pavimento == "Asfalto"
    assert p.extensao_m == 850.0
    assert p.largura_m == 12.0


def test_detectar_pontes_nunca_fabrica_vao_livre_a_partir_de_zero_sentinela(monkeypatch):
    # vaolivreho/vaovertica/cargasupor não fazem parte do dataclass Ponte
    # (achado da auditoria: onde presentes na base real, o único valor
    # observado é 0.0 — sentinela de "não medido", não uma medição real).
    # extensao/largura=0.0 pela mesma razão devem virar None, não "0m".
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Ponte Zero", "distancia_km": 0.1, "extensao": 0.0, "largura": 0.0}]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    ponte = rc._detectar_pontes_nos_cruzamentos([_cruzamento()], repo)[0]
    assert not hasattr(ponte, "vao_livre_horizontal_m")
    assert not hasattr(ponte, "carga_suportada")
    assert ponte.extensao_m is None
    assert ponte.largura_m is None


def test_cruzamento_hidrografico_drenagem_ganha_encoberto(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=5, filtros=None):
        if camada == "drenagem":
            return [{"nome": "Rio X", "distancia_km": 1.0, "encoberto": "Sim"}]
        return []

    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _fake)
    repo = rc.GeoIntelligenceRepository()
    achados = rc._detectar_cruzamentos_hidro([(0.0, 0.0, 0.0)], repo, 10.0, 10.0)
    rio = achados[0]
    assert rio["encoberto"] == "Sim"
    assert rio["artificial"] is None  # campo de massas_dagua não se aplica a drenagem


def test_cruzamento_hidrografico_massas_dagua_ganha_artificial_salgada_dominialidade(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=5, filtros=None):
        if camada == "massas_dagua":
            return [{"nome": "Lagoa Y", "distancia_km": 0.5, "artificial": "Sim",
                      "salgada": "Não", "dominialid": "Estadual/Distrital"}]
        return []

    monkeypatch.setattr(rc, "_consultar_camada_pesada_cacheada", _fake)
    repo = rc.GeoIntelligenceRepository()
    achados = rc._detectar_cruzamentos_hidro([(0.0, 0.0, 0.0)], repo, 10.0, 10.0)
    lagoa = achados[0]
    assert lagoa["artificial"] == "Sim"
    assert lagoa["salgada"] == "Não"
    assert lagoa["dominialidade"] == "Estadual/Distrital"
    assert lagoa["encoberto"] is None  # campo de drenagem não se aplica a massas_dagua


def test_detectar_feicoes_sem_campos_extra_atributos_fica_vazio(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Travessia X", "distancia_km": 1.0, "tipotransp": "Carga"}]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    achados = rc._detectar_feicoes([(0.0, 0.0, 0.0)], repo, "travessias", 10.0, "travessia", "fonte-teste")
    assert achados[0].atributos == {}  # sem campos_extra pedido -> nunca propaga nada extra


def test_detectar_feicoes_com_campos_extra_propaga_apenas_o_pedido(monkeypatch):
    def _fake(camada, lon, lat, raio_km=30.0, limite=10, filtros=None):
        return [{"nome": "Porto X", "distancia_km": 1.0, "tipotransp": "Misto",
                  "tipocomple": "Porto organizado", "campo_nao_pedido": "ignorar"}]

    monkeypatch.setattr(rc, "_consultar_rapido_camada_pequena", _fake)
    repo = rc.GeoIntelligenceRepository()
    achados = rc._detectar_feicoes(
        [(0.0, 0.0, 0.0)], repo, "complexos_portuarios", 10.0, "complexo portuário", "fonte-teste",
        campos_extra=("tipotransp", "tipocomple"))
    assert achados[0].atributos == {"tipotransp": "Misto", "tipocomple": "Porto organizado"}
    assert "campo_nao_pedido" not in achados[0].atributos


@pytestmark_dados
def test_analisar_rota_ponte_rio_niteroi_com_atributos_reais():
    origem = destino = (-22.8702, -43.1642)
    ctx = rc.analisar_rota(origem, destino, distancia_km=0.0, raio_km=6.0)
    ponte = next((p for p in ctx.pontes if "Rio-Niterói" in p.nome), None)
    assert ponte is not None
    assert isinstance(ponte, rc.Ponte)
    assert ponte.fonte == "IBGE BC250 (pontes)"


@pytestmark_dados
def test_analisar_rota_baia_guanabara_tem_atributos_massas_dagua():
    origem = destino = (-22.8702, -43.1642)
    ctx = rc.analisar_rota(origem, destino, distancia_km=0.0, raio_km=8.0)
    baia = next((c for c in ctx.corpos_dagua if "Guanabara" in c.nome), None)
    if baia is not None:
        assert baia.salgada in ("Sim", "Não", "Desconhecido", None)
        assert baia.encoberto is None  # atributo de drenagem, não de massas_dagua


# ==============================================================================
# Missão 2 / Rodada 6 — código de sub-bacia SNIRH (subBaciaCodigo), campo
# real presente em snirh_rios.csv desde sempre mas nunca lido antes.
# ==============================================================================

def test_subbacia_codigo_do_rio_conhecido_e_sem_ambiguidade():
    # Mesmo rio/caso não-ambíguo já usado para bacia_do_rio.
    assert rc.subbacia_codigo_do_rio("Rio Solimões-Amazonas") == "10"
    assert rc.subbacia_codigo_do_rio("rio solimoes-amazonas") == "10"  # normalização


def test_subbacia_codigo_do_rio_homonimo_com_subbacias_distintas_fica_none():
    # "Igarapé São Raimundo" existe em 3 registros no SNIRH, todos na mesma
    # bacia (RIO AMAZONAS) mas com subBaciaCodigo DIFERENTE (10 e 15) —
    # ambíguo o bastante para não escolher um dos dois arbitrariamente,
    # mesmo que bacia_do_rio consiga resolver o nível 1 (bacia) sem problema.
    assert rc.bacia_do_rio("Igarapé São Raimundo") == "RIO AMAZONAS"
    assert rc.subbacia_codigo_do_rio("Igarapé São Raimundo") is None


def test_subbacia_codigo_do_rio_desconhecido_e_vazio():
    assert rc.subbacia_codigo_do_rio("Rio Que Nao Existe Em Nenhuma Base 123") is None
    assert rc.subbacia_codigo_do_rio("") is None
    assert rc.subbacia_codigo_do_rio(None) is None


def test_subbacia_codigo_nunca_e_confundido_com_nome():
    # Nunca deve parecer um nome de bacia — só dígitos (às vezes múltiplos,
    # separados por vírgula quando há mais de um rio na rota).
    cod = rc.subbacia_codigo_do_rio("Rio Solimões-Amazonas")
    assert cod.isdigit()


@pytestmark_dados
def test_analisar_rota_sub_bacia_quando_presente_e_so_codigo_nunca_nome():
    origem = destino = (-3.1190, -60.0217)
    ctx = rc.analisar_rota(origem, destino, distancia_km=45.0, raio_km=10.0)
    if ctx.sub_bacia is not None:
        assert ctx.sub_bacia.startswith("Código(s) SNIRH: ")
        # a parte depois do prefixo só tem dígitos e ", " como separador
        resto = ctx.sub_bacia.replace("Código(s) SNIRH: ", "")
        assert all(c.isdigit() or c in ", " for c in resto)


# ==============================================================================
# Missão 2 / Rodada 7 — índice de complexidade geográfica (campo existia no
# contrato desde a Rodada 3 mas nunca era calculado).
# ==============================================================================

def test_indice_complexidade_rota_simples_sem_evidencias_e_zero():
    assert rc._indice_complexidade_geografica([], [], [], [], [], [], [], [], 0) == 0


def test_indice_complexidade_cresce_com_cruzamentos_hidrograficos():
    rio = rc.CruzamentoHidrografico(nome="Rio A", camada="drenagem", distancia_eixo_km=1.0,
                                     km_desde_origem=0.0, km_ate_destino=None, navegavel=None,
                                     regime=None, bacia=None, fonte="teste", confianca="alta")
    sem_rio = rc._indice_complexidade_geografica([], [], [], [], [], [], [], [], 0)
    com_rio = rc._indice_complexidade_geografica([rio], [], [], [], [], [], [], [], 0)
    assert com_rio > sem_rio


def test_indice_complexidade_penaliza_cruzamento_sem_confirmacao():
    rio = rc.CruzamentoHidrografico(nome="Rio A", camada="drenagem", distancia_eixo_km=1.0,
                                     km_desde_origem=0.0, km_ate_destino=None, navegavel=None,
                                     regime=None, bacia=None, fonte="teste", confianca="alta")
    ponte = rc.Ponte(nome="Ponte A", distancia_eixo_km=0.5, km_desde_origem=0.0,
                      tipo_ponte=None, tipo_pavimento=None, extensao_m=None, largura_m=None)
    sem_confirmacao = rc._indice_complexidade_geografica([rio], [], [], [], [], [], [], [], 0)
    com_confirmacao = rc._indice_complexidade_geografica([rio], [], [ponte], [], [], [], [], [], 0)
    assert sem_confirmacao > com_confirmacao


def test_indice_complexidade_multiplas_rodovias_pesa_mais_que_uma_so():
    r1 = rc.Rodovia(sigla="BR-1", km_desde_origem=0.0, distancia_eixo_km=0.5,
                     jurisdicao=None, administra=None, concessionaria=None, revestimento=None,
                     tipo_pavimento=None, nr_pistas=None, nr_faixas=None, limite_velocidade_kmh=None)
    r2 = rc.Rodovia(sigla="BR-2", km_desde_origem=5.0, distancia_eixo_km=0.5,
                     jurisdicao=None, administra=None, concessionaria=None, revestimento=None,
                     tipo_pavimento=None, nr_pistas=None, nr_faixas=None, limite_velocidade_kmh=None)
    uma = rc._indice_complexidade_geografica([], [], [], [], [], [], [r1], [], 0)
    duas = rc._indice_complexidade_geografica([], [], [], [], [], [], [r1, r2], [], 0)
    assert duas > uma


def test_indice_complexidade_nunca_excede_100():
    muitos_rios = [rc.CruzamentoHidrografico(
        nome=f"Rio {i}", camada="drenagem", distancia_eixo_km=0.1, km_desde_origem=float(i),
        km_ate_destino=None, navegavel="Sim", regime=None, bacia=None, fonte="teste",
        confianca="alta") for i in range(20)]
    c = rc._indice_complexidade_geografica(muitos_rios, [], [], [], [], [], [], [], 100)
    assert 0 <= c <= 100


@pytestmark_dados
def test_analisar_rota_preenche_complexidade_geografica_com_dado_real():
    ctx = rc.analisar_rota((-23.55, -46.63), (-22.90, -43.20), distancia_km=430.0, raio_km=10.0)
    assert ctx.complexidade_geografica is not None
    assert 0 <= ctx.complexidade_geografica <= 100


# ==============================================================================
# Missão 2 / Rodada 9 — detecção de anomalias geoespaciais estruturadas
# (§25-26 da missão), formalizando sinais que já existiam como texto solto.
# ==============================================================================

def test_dentro_do_brasil_ponto_valido():
    assert rc._dentro_do_brasil(-15.78, -47.93) is True  # Brasília


def test_dentro_do_brasil_ponto_fora():
    assert rc._dentro_do_brasil(40.7, -74.0) is False  # Nova York


def test_dentro_do_brasil_entrada_invalida_nao_afirma_anomalia():
    assert rc._dentro_do_brasil("x", "y") is True  # sem certeza -> não afirma


def test_detectar_anomalias_coordenada_fora_do_brasil():
    anomalias = rc._detectar_anomalias(40.7, -74.0, 40.8, -74.1, 5.0, 5.0, [], [], [], [], None)
    categorias = {a.categoria for a in anomalias}
    assert "coordenada_origem_fora_do_brasil" in categorias
    assert "coordenada_destino_fora_do_brasil" in categorias


def test_detectar_anomalias_distancia_menor_que_linha_reta():
    anomalias = rc._detectar_anomalias(-23.55, -46.63, -22.90, -43.20, 50.0, 360.0, [], [], [], [], None)
    achado = next(a for a in anomalias if a.categoria == "distancia_menor_que_linha_reta")
    assert achado.severidade == "alta"


def test_detectar_anomalias_distancia_maior_que_linha_reta_nao_e_anomalia():
    # Rota real quase sempre é mais longa que a linha reta — isso é normal,
    # nunca deve virar anomalia.
    anomalias = rc._detectar_anomalias(-23.55, -46.63, -22.90, -43.20, 450.0, 360.0, [], [], [], [], None)
    assert not any(a.categoria == "distancia_menor_que_linha_reta" for a in anomalias)


def test_detectar_anomalias_cruzamento_sem_confirmacao():
    rio = rc.CruzamentoHidrografico(nome="Rio A", camada="drenagem", distancia_eixo_km=1.0,
                                     km_desde_origem=0.0, km_ate_destino=None, navegavel=None,
                                     regime=None, bacia="BACIA X", fonte="teste", confianca="alta")
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [rio], [], [], [], "BACIA X")
    assert any(a.categoria == "cruzamento_hidrografico_sem_confirmacao" for a in anomalias)


def test_detectar_anomalias_travessia_sem_corpo_dagua():
    trav = rc.Feicao(nome="Travessia X", tipo="travessia (balsa)", distancia_eixo_km=1.0,
                      km_desde_origem=0.0, fonte="teste")
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [trav], None)
    assert any(a.categoria == "travessia_sem_corpo_dagua_no_raio" for a in anomalias)


def test_detectar_anomalias_rota_limpa_sem_evidencias_fica_vazia():
    # Sem rios, sem travessias, sem coordenadas fora do Brasil, sem distância
    # impossível -> nenhuma anomalia (nunca fabrica um alerta sem motivo real).
    anomalias = rc._detectar_anomalias(-15.78, -47.93, -15.80, -47.90, 5.0, 4.0, [], [], [], [], None)
    assert anomalias == []


def test_detectar_anomalias_nunca_lanca_com_none():
    # fail-open: entradas ausentes/None não devem derrubar a função.
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, None, None, [], [], [], [], None)
    assert isinstance(anomalias, list)


@pytestmark_dados
def test_analisar_rota_preenche_anomalias_com_dado_real():
    ctx = rc.analisar_rota((-23.55, -46.63), (-22.90, -43.20), distancia_km=50.0, raio_km=10.0)
    assert isinstance(ctx.anomalias, list)
    assert all(isinstance(a, rc.Anomalia) for a in ctx.anomalias)
    assert any(a.categoria == "distancia_menor_que_linha_reta" for a in ctx.anomalias)


# ==============================================================================
# Missão 2 / Rodada 15 — atributos rodoviários/ferroviários adicionais
# (trafego/situacao_fisica em Rodovia; posicao_relativa/situacao_fisica em
# Ferrovia) e a nova categoria de anomalia derivada deles: infraestrutura que
# a própria base IBGE já cadastra como não operacional no eixo da rota.
# ==============================================================================

def _rodovia(sigla="BR-1", situacao_fisica=None):
    return rc.Rodovia(sigla=sigla, km_desde_origem=0.0, distancia_eixo_km=0.5,
                       jurisdicao=None, administra=None, concessionaria=None,
                       revestimento=None, tipo_pavimento=None, nr_pistas=None, nr_faixas=None,
                       limite_velocidade_kmh=None, situacao_fisica=situacao_fisica)


def _ferrovia(nome="Linha X", situacao_fisica=None):
    return rc.Ferrovia(nome=nome, km_desde_origem=0.0, distancia_eixo_km=0.5,
                        tipo_trecho=None, bitola=None, eletrificada=None, nr_linhas=None,
                        jurisdicao=None, administra=None, concessionaria=None,
                        situacao_fisica=situacao_fisica)


def test_detectar_anomalias_rodovia_abandonada_gera_anomalia_alta():
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [], None,
                                        [_rodovia(situacao_fisica="Abandonada")], [])
    achado = next(a for a in anomalias if a.categoria == "infraestrutura_nao_operacional")
    assert achado.severidade == "alta"
    assert "BR-1" in achado.descricao and "Abandonada" in achado.descricao


def test_detectar_anomalias_ferrovia_planejada_gera_anomalia_media():
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [], None,
                                        [], [_ferrovia(situacao_fisica="Planejada")])
    achado = next(a for a in anomalias if a.categoria == "infraestrutura_nao_operacional")
    assert achado.severidade == "media"
    assert "Linha X" in achado.descricao and "Planejada" in achado.descricao


def test_detectar_anomalias_rodovia_construida_nao_gera_anomalia():
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [], None,
                                        [_rodovia(situacao_fisica="Construída")], [])
    assert not any(a.categoria == "infraestrutura_nao_operacional" for a in anomalias)


def test_detectar_anomalias_situacao_desconhecida_nao_gera_anomalia():
    # "Desconhecida" não é evidência de que a via não existe, só de que a
    # situação não foi apurada -- não pode virar alerta (nunca inferir além
    # do que o dado realmente sustenta).
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [], None,
                                        [_rodovia(situacao_fisica="Desconhecida")],
                                        [_ferrovia(situacao_fisica=None)])
    assert not any(a.categoria == "infraestrutura_nao_operacional" for a in anomalias)


def test_detectar_anomalias_sem_rodovias_ferrovias_nao_lanca():
    # Compatibilidade com chamadores antigos que não passam os dois últimos
    # parâmetros (ambos opcionais, default None).
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [], None)
    assert isinstance(anomalias, list)


@pytestmark_dados
def test_analisar_rota_propaga_rodovias_e_ferrovias_para_deteccao_de_anomalias():
    # Prova de integração ponta a ponta: analisar_rota já passa rodovias e
    # ferrovias reais para _detectar_anomalias (não fica preso ao valor
    # default None do parâmetro opcional).
    ctx = rc.analisar_rota((-23.55, -46.63), (-22.90, -43.20), distancia_km=430.0, raio_km=10.0)
    assert isinstance(ctx.anomalias, list)
    # Nenhuma asserção sobre haver ou não infraestrutura não-operacional nesta
    # rota específica (dado real, pode mudar) -- só que a chamada não quebra
    # e retorna o tipo esperado mesmo com rodovias/ferrovias reais propagadas.


# ==============================================================================
# Missão 3 / Rodada 2 — cross-validação entre o flag de balsa do MOTOR DE
# ROTEAMENTO (parâmetro `balsa_reportada_motor`, informado de fora) e a
# travessia detectada de forma INDEPENDENTE por este módulo (interseção
# espacial real com a hidrografia IBGE). É o cenário central do módulo:
# pegar o que a API de roteamento não informou (§14 da missão).
# ==============================================================================

def _travessia(nome="Travessia X"):
    return rc.Feicao(nome=nome, tipo="travessia (balsa)", distancia_eixo_km=1.0,
                      km_desde_origem=0.0, fonte="teste")


def test_detectar_anomalias_motor_nao_reportou_balsa_mas_geo_intel_achou_travessia():
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [_travessia()], None,
                                        balsa_reportada_motor=False)
    achado = next(a for a in anomalias if a.categoria == "travessia_nao_reportada_pelo_motor_de_rotas")
    assert achado.severidade == "alta"
    assert "Travessia X" in achado.descricao


def test_detectar_anomalias_motor_reportou_balsa_sem_nenhuma_confirmacao_geografica():
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [], None,
                                        balsa_reportada_motor=True)
    achado = next(a for a in anomalias if a.categoria == "balsa_sem_confirmacao_geografica")
    assert achado.severidade == "media"


def test_detectar_anomalias_motor_e_geo_intel_concordam_nao_gera_anomalia_de_cruzamento():
    # Motor reportou balsa (True) E a análise geográfica confirma (há travessia
    # real) -- os dois lados concordam, não é uma anomalia de cruzamento.
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [_travessia()], None,
                                        balsa_reportada_motor=True)
    assert not any(a.categoria in ("travessia_nao_reportada_pelo_motor_de_rotas",
                                   "balsa_sem_confirmacao_geografica") for a in anomalias)


def test_detectar_anomalias_sem_dado_do_motor_nao_gera_anomalia_de_cruzamento():
    # balsa_reportada_motor=None (chamador não informou, o padrão de todo
    # chamador pré-existente) -- nunca fabrica um "não" que o motor de
    # roteamento não disse. Mesmo com travessia real detectada, sem dado do
    # motor para comparar não há cruzamento a fazer.
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [], [], [], [_travessia()], None)
    assert not any(a.categoria in ("travessia_nao_reportada_pelo_motor_de_rotas",
                                   "balsa_sem_confirmacao_geografica") for a in anomalias)


def test_detectar_anomalias_motor_reportou_balsa_mas_ha_rio_proximo_nao_gera_anomalia():
    # Motor reportou balsa e não há travessia mapeada, mas HÁ rio/corpo
    # d'água na área -- não é uma discordância forte (pode só ser uma camada
    # de travessias incompleta, não um erro do roteador), então não dispara
    # a categoria "sem nenhuma confirmação geográfica".
    rio = rc.CruzamentoHidrografico(nome="Rio Y", camada="drenagem", distancia_eixo_km=1.0,
                                     km_desde_origem=0.0, km_ate_destino=None, navegavel=None,
                                     regime=None, bacia=None, fonte="teste", confianca="media")
    anomalias = rc._detectar_anomalias(0.0, 0.0, 0.0, 0.0, 10.0, 10.0, [rio], [], [], [], None,
                                        balsa_reportada_motor=True)
    assert not any(a.categoria == "balsa_sem_confirmacao_geografica" for a in anomalias)


def test_analisar_rota_aceita_balsa_reportada_motor_sem_lancar():
    # Fail-open: parâmetro novo não pode quebrar a chamada mesmo com
    # coordenadas inválidas ou qualquer outro caminho de erro.
    ctx = rc.analisar_rota((0.0, 0.0), (0.0, 0.0), balsa_reportada_motor=True)
    assert isinstance(ctx.anomalias, list)


@pytestmark_dados
def test_analisar_rota_propaga_balsa_reportada_motor_para_deteccao_de_anomalias():
    # Prova de integração ponta a ponta com dado real: BR-116 SP<->RJ (sem
    # travessia conhecida) + balsa_reportada_motor=True deve gerar a
    # anomalia de discordância (o motor "reportou" balsa que a análise
    # geográfica real não sustenta nesse eixo).
    ctx = rc.analisar_rota((-23.55, -46.63), (-22.90, -43.20), distancia_km=430.0, raio_km=10.0,
                           balsa_reportada_motor=True)
    assert isinstance(ctx.anomalias, list)
    if not ctx.rios_detectados and not ctx.corpos_dagua and not ctx.travessias:
        assert any(a.categoria == "balsa_sem_confirmacao_geografica" for a in ctx.anomalias)


# ==============================================================================
# _fonte_real — Missão 3, Rodada 17, §39: usa fonte_base/fonte_uf REAIS do
# registro quando presentes, nunca inventa especificidade que a base não informa.
# ==============================================================================

def test_fonte_real_usa_fonte_base_quando_presente():
    item = {"fonte_base": "BC250", "fonte_uf": ""}
    assert rc._fonte_real(item, "IBGE BC250/BC100 (drenagem)") == "IBGE BC250 (drenagem)"


def test_fonte_real_suprime_uf_br_da_base_nacional():
    # "BR" é o valor real de fonte_uf quando a origem é a BC250 (nacional) -- não é
    # uma UF de verdade, não deve aparecer como sufixo redundante.
    item = {"fonte_base": "BC250", "fonte_uf": "BR"}
    assert rc._fonte_real(item, "IBGE BC250/BC100 (pontes)") == "IBGE BC250 (pontes)"


def test_fonte_real_inclui_uf_quando_base_e_regional():
    item = {"fonte_base": "BC100", "fonte_uf": "RS"}
    assert rc._fonte_real(item, "IBGE BC250/BC100 (rodovias)") == "IBGE BC100 (rodovias) — RS"


def test_fonte_real_cai_no_fallback_quando_fonte_base_ausente():
    assert rc._fonte_real({}, "IBGE BC250/BC100 (pontes)") == "IBGE BC250/BC100 (pontes)"
    assert rc._fonte_real({"fonte_base": None}, "IBGE BC250/BC100 (pontes)") == "IBGE BC250/BC100 (pontes)"


def test_fonte_real_fallback_sem_parenteses_nao_lanca():
    # fallback sem "(" -- defensivo, nunca deve lançar mesmo em formato inesperado.
    assert rc._fonte_real({"fonte_base": "BC250"}, "fonte generica") == "IBGE BC250 (fonte generica)"


# ==============================================================================
# _detectar_cruzamentos_hidro — corroboração entre fontes (Missão 3, Rodada 18, §40):
# quando o MESMO nome normalizado é encontrado por extrações fonte_base DISTINTAS
# (BC250 e BC100 se sobrepõem em 7 UFs — construir_bases_locais_ibge.py), marca
# `confirmado_por` e eleva a confiança para "alta". Repo falso (sem tocar disco).
# ==============================================================================

class _RepoFake:
    """Repo mínimo: repo.consultar(camada, lat, lon, raio_km, limite) -> list[dict]."""
    def __init__(self, respostas_por_ponto):
        self._respostas = respostas_por_ponto  # lista de listas de itens, uma por ponto
        self._i = 0

    def consultar(self, camada, lat, lon, raio_km=30.0, limite=10, filtros=None):
        if camada != "drenagem":
            return []  # só avança o índice nas chamadas de "drenagem" (_CAMADAS_HIDRO tem 2 camadas)
        if self._i >= len(self._respostas):
            return []
        _r = self._respostas[self._i]
        self._i += 1
        return _r


def test_detectar_cruzamentos_hidro_marca_confirmado_por_duas_fontes_distintas():
    # Ponto 1: BC250 encontra "Rio Confirmado" a 1.0 km. Ponto 2: BC100 encontra o
    # MESMO nome (normalizado) a 0.8 km -- fontes distintas, mesmo rio real.
    repo = _RepoFake([
        [{"nome": "Rio Confirmado", "distancia_km": 1.0, "fonte_base": "BC250", "fonte_uf": "BR"}],
        [{"nome": "Rio Confirmado", "distancia_km": 0.8, "fonte_base": "BC100", "fonte_uf": "RS"}],
    ])
    pontos = [(-30.0, -51.0, 0.0), (-30.1, -51.1, 10.0)]
    achados = rc._detectar_cruzamentos_hidro(pontos, repo, raio_km=5.0, distancia_total_km=20.0)
    assert len(achados) == 1
    a = achados[0]
    assert a["confirmado_por"] == "BC100, BC250"
    assert a["confianca"] == "alta"
    # o vencedor por distância continua sendo o de MENOR distância (BC100, 0.8km) --
    # a corroboração não muda qual registro "vence", só acrescenta o sinal de confiança.
    assert a["distancia_eixo_km"] == 0.8


def test_detectar_cruzamentos_hidro_uma_fonte_so_nao_marca_confirmado_por():
    # Duas leituras do MESMO ponto pela MESMA extração (ex.: dois pontos amostrados
    # próximos) não é corroboração entre fontes -- é só a mesma fonte vista de novo.
    repo = _RepoFake([
        [{"nome": "Rio Solo", "distancia_km": 2.0, "fonte_base": "BC250", "fonte_uf": "BR"}],
        [{"nome": "Rio Solo", "distancia_km": 1.5, "fonte_base": "BC250", "fonte_uf": "BR"}],
    ])
    pontos = [(-30.0, -51.0, 0.0), (-30.1, -51.1, 10.0)]
    achados = rc._detectar_cruzamentos_hidro(pontos, repo, raio_km=5.0, distancia_total_km=20.0)
    assert len(achados) == 1
    assert achados[0]["confirmado_por"] is None
    assert achados[0]["confianca"] == "media"  # 1.5km > max(0.5, 5*0.15)=0.75 -> não é "alta" por proximidade


def test_detectar_cruzamentos_hidro_rios_diferentes_nunca_marcados_como_confirmados():
    # Nomes DIFERENTES -> achados DIFERENTES, cada um com sua própria fonte única --
    # nunca "confirma" um rio com a fonte de outro rio.
    repo = _RepoFake([
        [{"nome": "Rio A", "distancia_km": 1.0, "fonte_base": "BC250", "fonte_uf": "BR"}],
        [{"nome": "Rio B", "distancia_km": 1.0, "fonte_base": "BC100", "fonte_uf": "GO"}],
    ])
    pontos = [(-16.0, -49.0, 0.0), (-16.1, -49.1, 10.0)]
    achados = rc._detectar_cruzamentos_hidro(pontos, repo, raio_km=5.0, distancia_total_km=20.0)
    assert len(achados) == 2
    assert all(a["confirmado_por"] is None for a in achados)
