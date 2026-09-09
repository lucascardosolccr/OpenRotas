"""
Catálogo REAL das fontes de dados e APIs efetivamente usadas pelo OpenRotas.

Rodada 2 da missão "Extração máxima de APIs, datasets e fontes": este módulo
substitui uma versão anterior que registrava 40+ fontes com metadados
FABRICADOS (contagens de registros inventadas, `api_endpoint` para agências
— ANTAQ/DNIT/ANTT/DER — que a aplicação nunca chama, datas de "último teste"
e tempos de resposta que nunca foram medidos). Essa versão nunca era
carregada em runtime (`populate_sources()` não tinha nenhum chamador) — era
documentação morta e, pior, incorreta.

Esta reescrita segue uma auditoria real do código (grep de `requests.`/
`httpx`/`urllib` em todo o repositório, leitura de `manifest.json`, inspeção
de schema dos Parquet via `pyarrow`, contagem de linhas/colunas dos CSVs
locais) — cada entrada abaixo é rastreável a um arquivo:função específico.
Cada fonte declara `modo_acesso`:
  "api_rest_ao_vivo"     — a aplicação faz uma chamada HTTP de verdade hoje.
  "arquivo_local"        — dado já baixado/derivado, lido do disco.
  "download_sob_demanda" — arquivo grande baixado uma vez sob clique do
                            usuário (GitHub Release), depois lido do disco.
  "informativo_apenas"   — aparece na UI (link, texto, comando de exemplo)
                            mas NUNCA é de fato consultado pelo código.

Achado importante da auditoria (ver `uso_no_motor` de cada entrada): ANTAQ,
DNIT, ANTT e os DERs estaduais NÃO têm integração própria nesta aplicação.
Os dados que a UI antiga atribuía a essas agências são, na verdade, colunas
(`jurisdicao`, `administra`, `concession` etc.) dentro do BC250/BC100 do
IBGE (que É a fonte real desses trechos rodoviários/hidroviários). Por isso
elas não aparecem como fontes próprias aqui — o registro não fabrica uma
integração que não existe.
"""

import json
from datetime import datetime

from inteligencia_geoespacial.fontes_registry import SourceRegistry, SourcesRegistry, SourceStatus


def populate_sources() -> SourcesRegistry:
    """Popula e devolve um SourcesRegistry com as fontes REAIS identificadas
    na auditoria da Rodada 1/2 (missão "extração máxima"). Nenhuma fonte
    aqui é fabricada: todo `registros_totais` vem de manifest.json ou de
    contagem direta do arquivo; todo `api_endpoint` corresponde a uma
    chamada HTTP real no código (ou é `None`)."""
    registry = SourcesRegistry()

    # =====================================================================
    # BASE CARTOGRÁFICA CONTÍNUA DO IBGE (BC250/BC100) — 12 camadas locais
    # derivadas, lidas via inteligencia_geoespacial/bases_locais.py.
    # Fonte original: geoftp.ibge.gov.br (baixada e processada OFFLINE por
    # construir_bases_locais_ibge.py — não é uma chamada de rede em runtime).
    # =====================================================================

    _camadas_ibge = [
        ("pontes", 14812, "rodoviario",
         "route_context._detectar_pontes_nos_cruzamentos (pontes NO cruzamento hidrográfico); "
         "validators.CoordinateValidator (digest tipoponte)",
         "tipo_geom, geometry_wkb, lon, lat, xmin/ymin/xmax/ymax, fonte_base, fonte_uf, nome, "
         "matconstr, operaciona, situacaofi, largura, extensao, nrfaixas, nrpistas, posicaopis, "
         "tipopavime, tipoponte, vaolivreho, vaovertica, cargasupor"),
        ("travessias", 4046, "aquaviario",
         "route_context._detectar_aquaviario (travessias/balsas reais na rota); "
         "enrichment_engine (tipoembarc)",
         "...+ nome, tipotraves, tipouso, tipoembarc"),
        ("hidrovias", 179, "aquaviario",
         "route_context._detectar_aquaviario (hidrovias próximas ao corredor)",
         "...+ nome, operaciona, situacaofi, regime, extensaotr, caladomaxs"),
        ("atracadouros_terminal", 172, "aquaviario",
         "route_context._detectar_aquaviario (terminais/atracadouros próximos)",
         "...+ nome, tipoatraca, administra, matconstr, operaciona, situacaofi, aptidaoope"),
        ("complexos_portuarios", 171, "aquaviario",
         "route_context._detectar_aquaviario (portos próximos, índice de dependência aquaviária)",
         "...+ nome, modaluso, administra, jurisdicao, concession, operaciona, situacaofi, "
         "tipotransp, tipocomple, portosempa"),
        ("eclusas", 22, "aquaviario",
         "route_context._detectar_aquaviario",
         "...+ nome, desnivel, largura, extensao, calado, matconstr, operaciona, situacaofi"),
        ("sinalizacao", 388, "aquaviario",
         "Não consultada pelo route_context.py hoje — só exposta na aba manual 'Geoespacial IBGE'",
         "...+ nome, tiposinal, operaciona, situacaofi"),
        ("rodovias", 287136, "rodoviario",
         "Não consultada pelo route_context.py hoje — só exposta na aba manual 'Geoespacial IBGE' "
         "(287 mil trechos, camada pesada/bootstrap, ver AUDIT-ROD-01)",
         "...+ tipovia, jurisdicao, administra, concession, revestimen, operaciona, situacaofi, "
         "canteirodi, nrpistas, nrfaixas, trafego, tipopavime, sigla, acostament, codtrechor, "
         "limitevelo, emperimetr, nome"),
        ("ferrovias", 889, "ferroviario",
         "Não consultada pelo route_context.py hoje — só exposta na aba manual 'Geoespacial IBGE'",
         "...+ nome, codtrechof, posicaorel, tipotrecho, bitola, eletrifica, nrlinhas, jurisdicao, "
         "administra, concession, operaciona, situacaofi"),
        ("massas_dagua", 64850, "hidrografia",
         "route_context._detectar_cruzamentos_hidro (corpos d'água atravessados pela rota)",
         "...+ nome, tipomassad, regime, salgada, dominialid, artificial, possuitrec"),
        ("drenagem", 2181288, "hidrografia",
         "route_context._detectar_cruzamentos_hidro (rios atravessados pela rota — camada pesada, "
         "451MB, cache de janela ampla desde a Rodada 14)",
         "...+ nome, tipotrecho, navegavel, larguramed, regime, encoberto"),
        ("municipios", 5571, "territorial",
         "bases_locais.municipio_do_ponto (point-in-polygon, validação geográfica)",
         "...+ nome, geocodigo, anoderefer"),
    ]
    for _camada, _n, _cat, _uso, _campos in _camadas_ibge:
        registry.register(SourceRegistry(
            id=f"ibge_bc250_{_camada}",
            nome=f"IBGE BC250/BC100 — camada '{_camada}'",
            orgao="IBGE",
            categoria=_cat,
            dataset_url="https://geoftp.ibge.gov.br/cartas_e_mapas/bases_cartograficas_continuas/bc250/",
            api_endpoint=None,
            api_docs_url="https://www.ibge.gov.br/geociencias/cartas-e-mapas/bases-cartograficas-continuas.html",
            formato="Parquet (geometria WKB, EPSG:4326)",
            tipo_geometria="Point/LineString/Polygon (varia por camada)",
            sistema_coordenadas="EPSG:4326",
            cobertura_geografica="Brasil (BC250 nacional + BC100 para AC/AL/BA/ES/GO-DF/RS/RR/SE)",
            registros_totais=_n,
            data_atualizacao=datetime(2025, 3, 3),  # versão do shapefile fonte (bc_250_shapefiles_2026_03_03 é o build, dado é v2025)
            periodicidade="Ad-hoc (nova versão IBGE, reprocessada manualmente por construir_bases_locais_ibge.py)",
            qualidade={"completude": 1.0, "acuracia": 0.95},
            licenca="Domínio público (dados oficiais IBGE)",
            atribuicao_obrigatoria="IBGE — Base Cartográfica Contínua",
            restricoes="Nenhuma",
            campos_disponiveis=[c.strip() for c in _campos.replace("...+ ", "").split(",")],
            status=SourceStatus.ATIVO,
            data_ultimo_teste=None,  # arquivo local — não há "chamada" para medir tempo de resposta
            tempo_resposta_ms=None,
            proxima_validacao=datetime(2026, 12, 1),
            notas="Baixada e processada OFFLINE (build-time) por construir_bases_locais_ibge.py — "
                  "não é uma chamada de rede em runtime. manifest.json em data/brasil/ibge/derivadas/ "
                  "tem o registro oficial de quando foi gerada.",
            responsavel_validacao=None,
            modo_acesso="arquivo_local",
            uso_no_motor=_uso,
        ))

    # =====================================================================
    # ANA / SNIRH — hidrografia (rios e bacias vendorizados; estações sob demanda)
    # =====================================================================

    registry.register(SourceRegistry(
        id="ana_snirh_rios_csv",
        nome="ANA/SNIRH — Catálogo de Rios (snirh_rios.csv)",
        orgao="ANA (Agência Nacional de Águas)",
        categoria="hidrografia",
        dataset_url="https://www.snirh.gov.br/hidroweb/",
        api_endpoint=None,
        api_docs_url="https://www.snirh.gov.br/",
        formato="CSV",
        tipo_geometria=None,
        sistema_coordenadas=None,
        cobertura_geografica="Brasil",
        registros_totais=14136,
        data_atualizacao=None,
        periodicidade="Desconhecida (extrato estático vendorizado)",
        qualidade={"completude": 0.9},
        licenca="Domínio público (dados oficiais ANA)",
        atribuicao_obrigatoria="ANA/SNIRH",
        restricoes="Nenhuma",
        campos_disponiveis=["_links", "baciaCodigo", "dataAlt", "dataIns", "importado",
                             "importadoRepetido", "jurisdicao", "nome", "registroID", "removido",
                             "respAlt", "subBaciaCodigo", "temporario"],
        status=SourceStatus.ATIVO,
        data_ultimo_teste=None,
        tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Lido localmente via pandas. Usa apenas 'nome' e 'baciaCodigo' hoje "
              "(route_context._carregar_mapa_rio_bacia) — as outras 11 colunas, incluindo "
              "'subBaciaCodigo', não são lidas por nenhum código (ver Rodada 6/AUDIT-SUBBACIA-01).",
        responsavel_validacao=None,
        modo_acesso="arquivo_local",
        uso_no_motor="route_context._carregar_mapa_rio_bacia (join nome→bacia, exclui rios "
                     "homônimos ambíguos por design); UI da aba Hidrografia (tabela)",
    ))

    registry.register(SourceRegistry(
        id="ana_snirh_bacias_csv",
        nome="ANA/SNIRH — Catálogo de Bacias (snirh_bacias.csv)",
        orgao="ANA (Agência Nacional de Águas)",
        categoria="hidrografia",
        dataset_url="https://www.snirh.gov.br/hidroweb/",
        api_endpoint=None,
        api_docs_url="https://www.snirh.gov.br/",
        formato="CSV",
        tipo_geometria=None,
        sistema_coordenadas=None,
        cobertura_geografica="Brasil",
        registros_totais=9,
        data_atualizacao=None,
        periodicidade="Desconhecida (extrato estático vendorizado)",
        qualidade={"completude": 1.0},
        licenca="Domínio público (dados oficiais ANA)",
        atribuicao_obrigatoria="ANA/SNIRH",
        restricoes="Nenhuma",
        campos_disponiveis=["_links", "codigoNome", "dataAlt", "dataIns", "importado",
                             "importadoRepetido", "nome", "registroID", "removido", "respAlt",
                             "temporario"],
        status=SourceStatus.ATIVO,
        data_ultimo_teste=None,
        tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="9 bacias hidrográficas oficiais (nível nacional). Usa apenas 'registroID' e 'nome'.",
        responsavel_validacao=None,
        modo_acesso="arquivo_local",
        uso_no_motor="route_context._carregar_mapa_rio_bacia (código da bacia → nome oficial)",
    ))

    registry.register(SourceRegistry(
        id="ana_snirh_estacoes_csv",
        nome="ANA/SNIRH — Catálogo de Estações Hidrológicas (snirh_estacaos.csv)",
        orgao="ANA (Agência Nacional de Águas)",
        categoria="hidrografia",
        dataset_url="https://github.com/lucascardosolccr/openrotas-dados/releases/download/dados-geoespaciais-v1/snirh_estacaos.csv",
        api_endpoint=None,
        api_docs_url="https://www.snirh.gov.br/",
        formato="CSV (~91 MB)",
        tipo_geometria=None,
        sistema_coordenadas=None,
        cobertura_geografica="Brasil",
        registros_totais=None,  # não verificável sem baixar; nunca fabricar uma contagem
        data_atualizacao=None,
        periodicidade="Desconhecida (extrato estático vendorizado)",
        qualidade={},
        licenca="Domínio público (dados oficiais ANA)",
        atribuicao_obrigatoria="ANA/SNIRH",
        restricoes="Nenhuma",
        campos_disponiveis=["codigo", "nome", "rio", "bacia", "uf", "lat/latitude",
                             "lon/longitude", "tipo"],
        status=SourceStatus.ATIVO,
        data_ultimo_teste=None,
        tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Grande demais para o repositório principal (limite de 100MB do GitHub) — baixado "
              "sob demanda pelo botão 'Baixar catálogo completo de estações' na aba Hidrografia. "
              "Sem o download, a UI usa um pequeno dataset de fallback claramente rotulado como tal.",
        responsavel_validacao=None,
        modo_acesso="download_sob_demanda",
        uso_no_motor="Aba Hidrografia — tabela de estações (streamlit_app.py:_carregar_estacoes_com_fallback)",
    ))

    # =====================================================================
    # Grafo fluvial pré-computado (Rodada anterior: rios navegáveis, ANA
    # Ottocodificada + IBGE BC250 + Natural Earth, mesclados offline)
    # =====================================================================

    registry.register(SourceRegistry(
        id="grafo_fluvial_nacional",
        nome="Grafo de roteamento fluvial nacional (hidrografia_nacional.pkl.gz)",
        orgao="ANA + IBGE + Natural Earth (mesclado offline)",
        categoria="hidrografia",
        dataset_url="https://github.com/lucascardosolccr/Hidrografia",
        api_endpoint=None,
        api_docs_url=None,
        formato="Pickle comprimido (grafo esparso)",
        tipo_geometria="Graph (nós = coordenadas, arestas = trechos navegáveis)",
        sistema_coordenadas="EPSG:4326",
        cobertura_geografica="Brasil",
        registros_totais=1467729,  # nós; 1.724.845 arestas, 9.569 nomes de rio
        data_atualizacao=None,
        periodicidade="Ad-hoc (rebuild manual via script externo não incluído neste repositório)",
        qualidade={},
        licenca="Domínio público (derivado de dados oficiais)",
        atribuicao_obrigatoria="ANA (Base Hidrográfica Ottocodificada) + IBGE BC250 + Natural Earth",
        restricoes="Nenhuma",
        campos_disponiveis=["coords (nós)", "e (arestas)", "w (pesos)", "en (índice de nomes por "
                             "aresta)", "names (9.569 nomes de rio)"],
        status=SourceStatus.ATIVO,
        data_ultimo_teste=None,
        tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Construído por um script externo (construir_grafo_hidrografia_nacional.py, não "
              "presente neste repositório) a partir de 3 fontes distintas. Há um fallback de "
              "download remoto (_URL_GRAFO_FLUVIAL) nunca configurado em produção.",
        responsavel_validacao=None,
        modo_acesso="arquivo_local",
        uso_no_motor="streamlit_app._carregar_grafo_fluvial — estimativa de distância fluvial sob demanda",
    ))

    registry.register(SourceRegistry(
        id="natural_earth_rivers",
        nome="Natural Earth — Rivers & Lake Centerlines (10m/110m)",
        orgao="Natural Earth (domínio público, naturalearthdata.com)",
        categoria="hidrografia",
        dataset_url="https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-rivers-lake-centerlines/",
        api_endpoint=None,
        api_docs_url="https://www.naturalearthdata.com/",
        formato="Shapefile",
        tipo_geometria="LineString",
        sistema_coordenadas="EPSG:4326",
        cobertura_geografica="Global (usado apenas o recorte Brasil)",
        registros_totais=2129,
        data_atualizacao=None,
        periodicidade="Estática (dataset público versionado por release do Natural Earth)",
        qualidade={},
        licenca="Domínio público (CC0/Public Domain, Natural Earth)",
        atribuicao_obrigatoria="Nenhuma (mas creditado por boa prática)",
        restricoes="Nenhuma",
        campos_disponiveis=["nome do rio", "geometria (LineString)"],
        status=SourceStatus.ATIVO,
        data_ultimo_teste=None,
        tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Não é lido diretamente em runtime pelo streamlit_app.py — foi o insumo de build do "
              "grafo fluvial nacional (mesclagem offline, 'merge 433ª'). Os shapefiles brutos "
              "(ne_rivers/, ne_rivers_10m/) permanecem no repositório mas nenhum código os referencia "
              "diretamente hoje.",
        responsavel_validacao=None,
        modo_acesso="arquivo_local",
        uso_no_motor="Insumo de build do grafo fluvial (ver 'grafo_fluvial_nacional') — não lido em runtime",
    ))

    # =====================================================================
    # Motores de roteamento (chamadas HTTP reais)
    # =====================================================================

    _motores = [
        ("osrm_publico", "OSRM (instância pública project-osrm.org)", "OSRM / OpenStreetMap",
         "http://router.project-osrm.org", True,
         "distance, duration, geometry (polyline), legs[].steps[].maneuver.type (detecção de balsa), "
         "waypoints[].location/.distance (snap)",
         "streamlit_app.API_OSRM_Routing (routing), API_OSRM_Table (matriz), nearest-snap",
         "Chave configurável via secrets OSRM_URL; sessão dedicada com fallback de TLS."),
        ("osrm_fossgis", "OSRM (instância independente FOSSGIS)", "FOSSGIS e.V. / OpenStreetMap",
         "https://routing.openstreetmap.de/routed-car", True,
         "mesma forma do OSRM primário — usado para roteamento por consenso",
         "streamlit_app.API_OSRM_FOSSGIS_Routing",
         "Throttled a ≤1 req/s (FILA_OSRM2)."),
        ("google_routes_oficial", "Google Routes API v2 (computeRoutes, oficial)", "Google",
         "https://routes.googleapis.com/directions/v2:computeRoutes", True,
         "distanceMeters, duration, polyline.encodedPolyline (field mask restrito a esses 3 campos)",
         "streamlit_app.API_Google_Directions_Oficial",
         "Exige GOOGLE_MAPS_API_KEY (secrets) — desativado silenciosamente sem chave. "
         "travelAdvisory (pedágio/balsa) e alternativas NÃO são pedidos no field mask."),
        ("graphhopper", "GraphHopper Directions API", "GraphHopper GmbH",
         "https://graphhopper.com/api/1", True,
         "paths[].distance/.time/.points.coordinates, .details.road_environment (balsa)",
         "streamlit_app.API_GraphHopper_Routing",
         "Exige GRAPHHOPPER_API_KEY (secrets) salvo se URL self-hosted."),
        ("openrouteservice", "OpenRouteService (ORS) Directions API", "HeiGIT / openrouteservice.org",
         "https://api.openrouteservice.org/v2/directions/driving-car", True,
         "features[0].properties.summary.distance/.duration, .geometry.coordinates",
         "streamlit_app.API_ORS_Routing",
         "Exige ORS_API_KEY (secrets) — desativado sem chave."),
        ("valhalla", "Valhalla routing engine (instância pública FOSSGIS por padrão)", "Valhalla / FOSSGIS",
         "https://valhalla1.openstreetmap.de", True,
         "distância/tempo/shape do JSON de rota Valhalla (driving e multimodal)",
         "streamlit_app.API_Valhalla_Routing, API_Valhalla_Multimodal_Routing",
         "Throttled a ≤1 req/s (FILA_VALHALLA); URL configurável via secrets VALHALLA_URL."),
    ]
    for _id, _nome, _orgao, _url, _ativo, _campos, _uso, _nota in _motores:
        registry.register(SourceRegistry(
            id=_id, nome=_nome, orgao=_orgao, categoria="roteamento",
            dataset_url=_url, api_endpoint=_url, api_docs_url=None,
            formato="REST/JSON", tipo_geometria="LineString (polyline codificada)",
            sistema_coordenadas="EPSG:4326", cobertura_geografica="Global (rede OpenStreetMap ou proprietária)",
            registros_totais=None, data_atualizacao=None, periodicidade="Contínua (serviço ao vivo)",
            qualidade={}, licenca="Depende do provedor (ver termos de uso de cada serviço)",
            atribuicao_obrigatoria="Depende do provedor", restricoes="Sujeito a rate-limit/uso justo",
            campos_disponiveis=[c.strip() for c in _campos.split(",")],
            status=SourceStatus.ATIVO if _ativo else SourceStatus.EM_TESTE,
            data_ultimo_teste=None, tempo_resposta_ms=None, proxima_validacao=datetime(2026, 12, 1),
            notas=_nota, responsavel_validacao=None,
            modo_acesso="api_rest_ao_vivo", uso_no_motor=_uso,
        ))

    registry.register(SourceRegistry(
        id="google_maps_scrape_rotas",
        nome="Google Maps — scraping não-oficial de rotas (fallback)",
        orgao="Google (acesso não-oficial)",
        categoria="roteamento",
        dataset_url="https://www.google.com/maps/preview/directions",
        api_endpoint="https://www.google.com/maps/preview/directions",
        api_docs_url=None,
        formato="HTML/JS (extração por regex, não é JSON estruturado)",
        tipo_geometria=None,
        sistema_coordenadas=None,
        cobertura_geografica="Global",
        registros_totais=None,
        data_atualizacao=None,
        periodicidade="Contínua (mas frágil)",
        qualidade={},
        licenca="N/A — endpoint não-público, sujeito a bloqueio sem aviso",
        atribuicao_obrigatoria="N/A",
        restricoes="Uso não-oficial, adjacente aos Termos de Serviço do Google; auto-limitado por "
                    "circuit breaker no próprio código",
        campos_disponiveis=["distância e duração extraídas por regex do corpo da resposta"],
        status=SourceStatus.EM_TESTE,
        data_ultimo_teste=None,
        tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Técnica de scraping com rotação de User-Agent e 'priming' de sessão para cookies de "
              "consentimento. O próprio código já documenta a fragilidade e implementa um circuit "
              "breaker (_google_pode_chamar) que degrada para OSRM quando bloqueado.",
        responsavel_validacao=None,
        modo_acesso="api_rest_ao_vivo",
        uso_no_motor="streamlit_app._chamar_motor_cb (fallback quando a API oficial do Google não "
                     "está configurada)",
    ))

    # =====================================================================
    # Geocodificação e CEP
    # =====================================================================

    _geocoders = [
        ("tomtom_geocode", "TomTom Search/Geocode API", "TomTom",
         "https://api.tomtom.com/search/2/geocode", True,
         "results[].position.lat/lon, .address.municipality/countrySubdivision/neighbourhood/"
         "subdivision/streetName/streetNumber/postalCode",
         "streamlit_app.API_TomTom", "Exige TOMTOM_API_KEY (secrets)."),
        ("arcgis_geocode", "Esri ArcGIS World Geocoding Service (forward + reverse)", "Esri",
         "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer", False,
         "candidates[].location.x/y, .attributes.City/RegionAbbr/Neighborhood/StName/Address/"
         "AddNum/Postal (forward); address.Address/Neighborhood/City/RegionAbbr/Postal (reverse)",
         "streamlit_app.API_ArcGIS, executar_reverse_geocoding_multimotor, "
         "obter_coordenada_centroide_supremo",
         "Sem chave (serviço gratuito público). O campo 'score' de confiança do próprio ArcGIS "
         "não é lido — o app usa um score_base fixo de 30."),
        ("nominatim", "Nominatim (OpenStreetMap, instância pública demo)", "OSM Foundation",
         "https://nominatim.openstreetmap.org", False,
         "lat/lon, address.city/town/state/neighbourhood/suburb/road/house_number/postcode",
         "streamlit_app.API_Nominatim, executar_reverse_geocoding_multimotor, cascata_postal_tripla",
         "Throttled a ≤1 req/s (FILA_NOMINATIM) — política de uso justo da instância pública."),
        ("photon", "Photon (Komoot, geocodificador baseado em OSM)", "Komoot",
         "https://photon.komoot.io/api/", False,
         "features[].geometry.coordinates, .properties.city/state/district/street/housenumber/postcode",
         "streamlit_app.API_Photon", "Sem chave."),
    ]
    for _id, _nome, _orgao, _url, _keyed, _campos, _uso, _nota in _geocoders:
        registry.register(SourceRegistry(
            id=_id, nome=_nome, orgao=_orgao, categoria="geocodificacao",
            dataset_url=_url, api_endpoint=_url, api_docs_url=None,
            formato="REST/JSON", tipo_geometria="Point", sistema_coordenadas="EPSG:4326",
            cobertura_geografica="Global (uso restrito ao Brasil via filtro de país)",
            registros_totais=None, data_atualizacao=None, periodicidade="Contínua (serviço ao vivo)",
            qualidade={}, licenca="Depende do provedor", atribuicao_obrigatoria="Depende do provedor",
            restricoes="Rate-limit" + (" + chave de API" if _keyed else ""),
            campos_disponiveis=[c.strip() for c in _campos.split(",")],
            status=SourceStatus.ATIVO, data_ultimo_teste=None, tempo_resposta_ms=None,
            proxima_validacao=datetime(2026, 12, 1), notas=_nota, responsavel_validacao=None,
            modo_acesso="api_rest_ao_vivo", uso_no_motor=_uso,
        ))

    registry.register(SourceRegistry(
        id="google_maps_scrape_geocode",
        nome="Google Maps — scraping não-oficial de geocodificação (opt-in)",
        orgao="Google (acesso não-oficial)",
        categoria="geocodificacao",
        dataset_url="https://www.google.com/maps/search/",
        api_endpoint="https://www.google.com/maps/search/",
        api_docs_url=None,
        formato="HTML/JS (extração por regex)",
        tipo_geometria=None, sistema_coordenadas=None, cobertura_geografica="Global",
        registros_totais=None, data_atualizacao=None, periodicidade="Contínua (mas frágil)",
        qualidade={}, licenca="N/A", atribuicao_obrigatoria="N/A",
        restricoes="Uso não-oficial; opt-in explícito do usuário (usar_google_geocode)",
        campos_disponiveis=["lat/lon extraídos por regex (sem componentes de endereço)"],
        status=SourceStatus.EM_TESTE, data_ultimo_teste=None, tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Mesmo circuit breaker da versão de rotas (item 'google_maps_scrape_rotas').",
        responsavel_validacao=None, modo_acesso="api_rest_ao_vivo",
        uso_no_motor="streamlit_app.API_Google_Geocode (opt-in via flag de sessão)",
    ))

    _ceps = [
        ("brasilapi_cep", "BrasilAPI — CEP v2", "Comunidade (BrasilAPI, mantido por voluntários)",
         "https://brasilapi.com.br/api/cep/v2", "city, street, neighborhood, state, "
         "location.coordinates.latitude/longitude"),
        ("viacep", "ViaCEP", "Comunidade (ViaCEP)",
         "https://viacep.com.br/ws", "logradouro, bairro, localidade, uf"),
        ("opencep", "OpenCEP", "Comunidade (OpenCEP)",
         "https://opencep.com/v1", "logradouro, bairro, localidade, uf (mesmo formato do ViaCEP)"),
    ]
    for _id, _nome, _orgao, _url, _campos in _ceps:
        registry.register(SourceRegistry(
            id=_id, nome=_nome, orgao=_orgao, categoria="cep",
            dataset_url=_url, api_endpoint=_url, api_docs_url=None,
            formato="REST/JSON", tipo_geometria=None, sistema_coordenadas=None,
            cobertura_geografica="Brasil", registros_totais=None, data_atualizacao=None,
            periodicidade="Contínua (serviço ao vivo)", qualidade={},
            licenca="Comunidade / sem SLA formal", atribuicao_obrigatoria="Nenhuma",
            restricoes="Sem chave, mas sem garantia de disponibilidade (mantido por voluntários)",
            campos_disponiveis=[c.strip() for c in _campos.split(",")],
            status=SourceStatus.ATIVO, data_ultimo_teste=None, tempo_resposta_ms=None,
            proxima_validacao=datetime(2026, 12, 1),
            notas="Um de 3 provedores em cascata (cascata_postal_tripla) — usados em ordem até um responder.",
            responsavel_validacao=None, modo_acesso="api_rest_ao_vivo",
            uso_no_motor="streamlit_app.cascata_postal_tripla",
        ))

    # =====================================================================
    # IBGE — APIs REST ao vivo (distintas do BC250/BC100, que é arquivo local)
    # =====================================================================

    registry.register(SourceRegistry(
        id="ibge_localidades_api",
        nome="IBGE — API de Localidades (estados/municípios/distritos)",
        orgao="IBGE",
        categoria="territorial",
        dataset_url="https://servicodados.ibge.gov.br/api/v1/localidades",
        api_endpoint="https://servicodados.ibge.gov.br/api/v1/localidades",
        api_docs_url="https://servicodados.ibge.gov.br/api/docs/localidades",
        formato="REST/JSON",
        tipo_geometria=None, sistema_coordenadas=None, cobertura_geografica="Brasil",
        registros_totais=5571,
        data_atualizacao=None, periodicidade="Contínua (serviço ao vivo, cache local de 30 dias)",
        qualidade={"completude": 1.0}, licenca="Domínio público", atribuicao_obrigatoria="IBGE",
        restricoes="Nenhuma",
        campos_disponiveis=["sigla/nome (estados)", "nome, id (código IBGE), "
                             "microrregiao.mesorregiao.UF.sigla (municípios)",
                             "nome, id, municipio.nome, municipio.microrregiao.mesorregiao.UF.sigla (distritos)"],
        status=SourceStatus.ATIVO, data_ultimo_teste=None, tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="NÃO retorna latitude/longitude de municípios (confirmado no próprio código) — "
              "centróides vêm de outras fontes (ArcGIS/Nominatim/fallback GitHub). Meso/micro-região "
              "são buscadas mas só a sigla da UF é de fato aproveitada.",
        responsavel_validacao=None, modo_acesso="api_rest_ao_vivo",
        uso_no_motor="streamlit_app.carregar_dados_ibge (cache em municipios_ibge_v2.pkl, 30 dias)",
    ))

    registry.register(SourceRegistry(
        id="ibge_malhas_api",
        nome="IBGE — API de Malhas Territoriais (polígonos municipais, v3)",
        orgao="IBGE",
        categoria="territorial",
        dataset_url="https://servicodados.ibge.gov.br/api/v3/malhas",
        api_endpoint="https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{cod_ibge}",
        api_docs_url="https://servicodados.ibge.gov.br/api/docs/malhas",
        formato="GeoJSON",
        tipo_geometria="Polygon/MultiPolygon", sistema_coordenadas="EPSG:4326",
        cobertura_geografica="Brasil", registros_totais=5571,
        data_atualizacao=None, periodicidade="Contínua (cache de 24h via st.cache_data)",
        qualidade={}, licenca="Domínio público", atribuicao_obrigatoria="IBGE", restricoes="Nenhuma",
        campos_disponiveis=["features[].geometry (só os anéis de coordenadas são usados)"],
        status=SourceStatus.ATIVO, data_ultimo_teste=None, tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Alternativa/complemento ao ponto-em-polígono offline (camada 'municipios' do BC250) — "
              "usado como validador sob demanda, não no pipeline automático de rotas.",
        responsavel_validacao=None, modo_acesso="api_rest_ao_vivo",
        uso_no_motor="streamlit_app._ibge_malha_aneis / _validar_ponto_no_municipio (gated por "
                     "flag IBGE_MALHAS_ATIVO)",
    ))

    registry.register(SourceRegistry(
        id="github_municipios_brasileiros",
        nome="kelvins/municipios-brasileiros (GitHub, dataset comunitário)",
        orgao="Comunidade (mantenedor: kelvins)",
        categoria="territorial",
        dataset_url="https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/json/municipios.json",
        api_endpoint="https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/json/municipios.json",
        api_docs_url="https://github.com/kelvins/municipios-brasileiros",
        formato="JSON", tipo_geometria=None, sistema_coordenadas=None, cobertura_geografica="Brasil",
        registros_totais=5571, data_atualizacao=None,
        periodicidade="Estática (snapshot do repositório comunitário)",
        qualidade={}, licenca="Ver licença do repositório (dataset derivado do IBGE)",
        atribuicao_obrigatoria="kelvins/municipios-brasileiros", restricoes="Nenhuma",
        campos_disponiveis=["codigo_ibge", "nome", "codigo_uf", "latitude", "longitude"],
        status=SourceStatus.ATIVO, data_ultimo_teste=None, tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Único ponto do app que fornece latitude/longitude de município diretamente — a API "
              "oficial do IBGE (ibge_localidades_api) não traz essas coordenadas.",
        responsavel_validacao=None, modo_acesso="api_rest_ao_vivo",
        uso_no_motor="streamlit_app._carregar_municipios_fallback_github (fallback quando a API "
                     "IBGE falha/está incompleta; cache de 30 dias)",
    ))

    registry.register(SourceRegistry(
        id="sedes_oficiais_ibge_csv",
        nome="Sedes oficiais dos municípios (sedes_oficiais_ibge.csv)",
        orgao="IBGE",
        categoria="territorial",
        dataset_url="arquivo local vendorizado — origem: IBGE",
        api_endpoint=None, api_docs_url=None,
        formato="CSV", tipo_geometria="Point", sistema_coordenadas="EPSG:4326",
        cobertura_geografica="Brasil", registros_totais=5571, data_atualizacao=None,
        periodicidade="Estática", qualidade={"completude": 1.0}, licenca="Domínio público",
        atribuicao_obrigatoria="IBGE", restricoes="Nenhuma",
        campos_disponiveis=["codigo_ibge", "lat", "lon"],
        status=SourceStatus.ATIVO, data_ultimo_teste=None, tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Tabela mínima por design (3 colunas) — todas usadas. Tem fallback embutido em base64 "
              "(_SEDES_OFICIAIS_B64) para deploys em nuvem onde o CSV pode não estar presente.",
        responsavel_validacao=None, modo_acesso="arquivo_local",
        uso_no_motor="streamlit_app (lookup direto de centróide oficial por código IBGE)",
    ))

    # =====================================================================
    # Infraestrutura de dados (não é uma "fonte" temática, mas é onde os
    # arquivos pesados demais para o GitHub principal são hospedados)
    # =====================================================================

    registry.register(SourceRegistry(
        id="github_release_openrotas_dados",
        nome="GitHub Releases — lucascardosolccr/openrotas-dados (bootstrap de dados pesados)",
        orgao="Projeto OpenRotas (hospedagem própria)",
        categoria="infra_dados",
        dataset_url="https://github.com/lucascardosolccr/openrotas-dados/releases/download/dados-geoespaciais-v1/",
        api_endpoint=None, api_docs_url=None,
        formato="Parquet / CSV (download binário via urllib)",
        tipo_geometria=None, sistema_coordenadas=None, cobertura_geografica="Brasil",
        registros_totais=None, data_atualizacao=None,
        periodicidade="Ad-hoc (mesma cadência do build das camadas derivadas)",
        qualidade={}, licenca="Mesma licença dos dados de origem (IBGE/ANA)",
        atribuicao_obrigatoria="N/A (é hospedagem, não fonte de dados própria)",
        restricoes="Nenhuma",
        campos_disponiveis=["drenagem.parquet (451,4 MB)", "rodovias.parquet (121,7 MB)",
                             "snirh_estacaos.csv (91,1 MB)"],
        status=SourceStatus.ATIVO, data_ultimo_teste=None, tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="Existe só porque esses 3 arquivos excedem o limite de 100MB do GitHub para o "
              "repositório principal — não é uma fonte de dados original.",
        responsavel_validacao=None, modo_acesso="download_sob_demanda",
        uso_no_motor="inteligencia_geoespacial.dados_bootstrap.baixar_ausentes",
    ))

    # =====================================================================
    # Dado órfão encontrado na auditoria — sem nenhum código que o referencie
    # =====================================================================

    registry.register(SourceRegistry(
        id="localidades_brasil_shp_orfao",
        nome="Localidades_Brasil_shp.zip (arquivo órfão, 4,5 MB)",
        orgao="Desconhecido (não documentado)",
        categoria="orfao",
        dataset_url="arquivo local no repositório",
        api_endpoint=None, api_docs_url=None,
        formato="Shapefile (zip)", tipo_geometria=None, sistema_coordenadas=None,
        cobertura_geografica="Brasil (presumido pelo nome)", registros_totais=None,
        data_atualizacao=None, periodicidade="N/A",
        qualidade={}, licenca="Desconhecida", atribuicao_obrigatoria="Desconhecida",
        restricoes="Desconhecidas — origem não documentada",
        campos_disponiveis=[],
        status=SourceStatus.INATIVO, data_ultimo_teste=None, tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 12, 1),
        notas="grep em todo o repositório não encontrou NENHUMA referência de código a este "
              "arquivo. Candidato a remoção ou a ser documentado/integrado numa rodada futura — "
              "registrado aqui para não ficar invisível ao inventário (§21 da missão).",
        responsavel_validacao=None, modo_acesso="informativo_apenas",
        uso_no_motor="",
    ))

    return registry


# Instância pronta para uso — quem importar este módulo já recebe o catálogo real
# populado (ao contrário da versão anterior, onde populate_sources() nunca era chamada).
REGISTRO_REAL = populate_sources()


# ==============================================================================
# Saúde dos Dados (Rodada 11, Missão 2 — extração máxima §19): "FONTES ATIVAS,
# APIs FUNCIONAIS, DATASETS DISPONÍVEIS, DATASETS DESATUALIZADOS, COBERTURA,
# QUALIDADE, ÚLTIMA ATUALIZAÇÃO" — tudo a partir de checagens 100% LOCAIS
# (existência de arquivo, metadados de Parquet, manifest.json, mtime). Nunca
# faz uma chamada de rede: "APIs funcionais" aqui significa "declaradas como
# api_rest_ao_vivo no catálogo real" (Rodada 2), não um teste ao vivo — esta
# missão decidiu explicitamente não fazer novas chamadas de rede (§ decisão
# de escopo do bloco 1). "ERROS DE CONSULTA" do §19 da missão não é reportado
# aqui: exigiria telemetria de execução ao vivo que este projeto não mantém
# hoje — omitido em vez de fabricado.
# ==============================================================================

def saude_dos_dados() -> dict:
    """Relatório de saúde 100% local (sem rede) do conjunto de dados.
    Fail-open: qualquer falha parcial de leitura (arquivo corrompido,
    manifest ausente) aparece como campo `None`/lista vazia, nunca quebra
    o relatório inteiro nem inventa um valor."""
    import os

    registry = populate_sources()
    fontes = list(registry.sources.values())
    ativas = [s for s in fontes if s.status == SourceStatus.ATIVO]
    em_teste = [s for s in fontes if s.status == SourceStatus.EM_TESTE]
    apis_vivas = [s for s in fontes if s.modo_acesso == "api_rest_ao_vivo"]

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(raiz, "data", "brasil", "ibge", "derivadas", "manifest.json")
    manifest: dict = {}
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        manifest = {}

    camadas_status = []
    for camada, info in manifest.get("camadas", {}).items():
        caminho = os.path.join(raiz, "data", "brasil", "ibge", "derivadas", camada + ".parquet")
        existe = os.path.exists(caminho)
        registros_manifest = info.get("registros")
        registros_reais = None
        mtime = None
        if existe:
            try:
                import pyarrow.parquet as _pq
                registros_reais = _pq.ParquetFile(caminho).metadata.num_rows
            except Exception:
                registros_reais = None
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(caminho))
            except Exception:
                mtime = None
        camadas_status.append({
            "camada": camada,
            "existe": existe,
            "registros_manifest": registros_manifest,
            "registros_reais": registros_reais,
            "bate_com_manifest": (registros_reais == registros_manifest)
                                  if (existe and registros_reais is not None) else None,
            "ultima_modificacao": mtime,
        })

    bootstrap_ausentes: list = []
    try:
        from . import dados_bootstrap as _boot
        bootstrap_ausentes = _boot.ausentes()
    except Exception:
        bootstrap_ausentes = []

    completudes = [s.qualidade.get("completude") for s in fontes
                   if isinstance(s.qualidade, dict) and s.qualidade.get("completude") is not None]
    qualidade_media = (sum(completudes) / len(completudes)) if completudes else None

    return {
        "gerado_em": datetime.utcnow(),
        "fontes_catalogadas": len(fontes),
        "fontes_ativas": len(ativas),
        "fontes_em_teste": len(em_teste),
        "apis_ao_vivo": len(apis_vivas),
        "camadas_ibge": camadas_status,
        "camadas_com_arquivo_presente": sum(1 for c in camadas_status if c["existe"]),
        "camadas_total": len(camadas_status),
        "camadas_divergentes_do_manifest": [c["camada"] for c in camadas_status if c["bate_com_manifest"] is False],
        "bootstrap_ausentes": bootstrap_ausentes,
        "extraido_em_utc_manifest": manifest.get("extraido_em_utc"),
        "qualidade_media_completude": qualidade_media,
    }
