# -*- coding: utf-8 -*-
"""OpenRotas Desktop — testes da edição desktop (Etapa 6).

Cobre a lógica que NÃO depende de Windows/GUI/OSRM: configuração, perfil de desempenho,
resolução do motor (fallback defensivo), camada de dados locais e diagnóstico. Roda em
qualquer ambiente (inclusive este, Linux na nuvem) com `pytest desktop/tests`."""
import os
import sys
import pytest

_DESKTOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_DESKTOP, "app"))
sys.path.insert(0, _DESKTOP)
sys.path.insert(0, os.path.join(_DESKTOP, "data_local"))
sys.path.insert(0, os.path.join(_DESKTOP, "telemetry"))
sys.path.insert(0, os.path.join(_DESKTOP, "installer"))

import desktop_config as cfg          # noqa: E402
import diagnostics                    # noqa: E402
from engines import osrm_manager as osrm   # noqa: E402
import local_data                     # noqa: E402
from resources import resource_manager as rm   # noqa: E402
from resources import painel                    # noqa: E402
from resources import provisionamento as prov   # noqa: E402
from resources import central_dados             # noqa: E402
from audit import coverage_auditor as ca         # noqa: E402
from geo import repositorio as georepo            # noqa: E402
import exec_profile                   # noqa: E402
import app_update                     # noqa: E402


# ------------------------------- desktop_config -------------------------------
def test_app_root_tem_o_streamlit_app():
    assert (cfg.app_root() / "streamlit_app.py").exists()

def test_hardware_coerente():
    hw = cfg.detectar_hardware()
    assert hw["cpus"] >= 1
    assert hw["perfil"] in ("performance", "equilibrado", "economico")

def test_perfil_desempenho_dentro_dos_limites():
    p = cfg.perfil_desempenho()
    assert 8 <= p["workers_rota"] <= 32
    assert 512 <= p["cache_mb_sugerido"] <= 4096

def test_validar_config_service_role_e_erro():
    av = cfg.validar_config({"local_login": True, "SUPABASE_ANON_KEY": "eyJ...service_role...x"})
    assert any(n == "erro" and "service_role" in m for n, m in av)

def test_validar_config_docker_sem_grafo_avisa():
    av = cfg.validar_config({"local_login": True, "osrm": {"mode": "docker"}})
    assert any(n == "aviso" and "graph_url" in m for n, m in av)

def test_validar_config_supabase_ausente_sem_login_local():
    av = cfg.validar_config({"osrm": {"mode": "off"}})
    assert any(n == "aviso" and "SUPABASE" in m for n, m in av)

def test_validar_config_login_local_sem_supabase_ok():
    av = cfg.validar_config({"local_login": True, "osrm": {"mode": "off"}})
    assert not any("SUPABASE" in m for _, m in av)   # login local não exige Supabase

def test_validar_config_graph_url_com_mode_off_e_info():
    av = cfg.validar_config({"local_login": True, "osrm": {"mode": "off", "graph_url": "http://x/g.part00"}})
    assert any(n == "info" and "graph_url" in m for n, m in av)


def test_user_data_dir_e_resumo():
    paths = cfg.ensure_user_dirs()
    assert paths["cache"].exists()
    r = cfg.resumo_config()
    assert {"app_root", "hardware", "porta", "user_data"} <= set(r)

def test_bootstrap_config_cria_do_exemplo(tmp_path, monkeypatch):
    # 1º uso: cria desktop.json a partir do exemplo; 2ª chamada é no-op.
    monkeypatch.setattr(cfg, "user_data_dir", lambda: tmp_path)
    criado = cfg.bootstrap_config_usuario()
    destino = tmp_path / "config" / "desktop.json"
    assert criado == destino and destino.exists()
    import json as _json
    dados = _json.loads(destino.read_text(encoding="utf-8"))
    assert "SUPABASE_URL" in dados and "osrm" in dados     # veio do exemplo
    assert cfg.bootstrap_config_usuario() is None          # já existe → não recria

def test_caminho_exemplo_config_existe():
    assert cfg._caminho_exemplo_config() is not None       # o exemplo embarcado é encontrável


# ------------------------------- osrm_manager --------------------------------
def test_resolver_off_nao_mexe_na_url():
    r = osrm.resolver({"mode": "off"})
    assert r.modo == "off" and r.url is None and r.ativo is False

def test_resolver_external_sem_servidor_nao_quebra():
    r = osrm.resolver({"mode": "external", "url": "http://127.0.0.1:5999"})
    assert r.modo == "external" and r.ativo is False and r.url is None  # fallback ao público

def test_resolver_legado_osrm_url_tratado_como_external():
    r = osrm.resolver(None, osrm_url_legado="http://127.0.0.1:5999")
    assert r.modo == "external"

def test_resolver_modo_desconhecido_defensivo():
    r = osrm.resolver({"mode": "xpto"})
    assert r.ativo is False and r.url is None

def test_health_url_vazia_e_encerrar_noop():
    assert osrm.health("") is False
    osrm.encerrar(osrm.ResultadoMotor(url=None, modo="off", ativo=False))  # não levanta

def test_remover_container_nunca_levanta():
    osrm._remover_container("")                    # nome vazio → no-op
    osrm._remover_container("openrotas-osrm-inexistente")   # docker ausente → não levanta

def test_encerrar_gerenciado_sem_docker_nao_levanta():
    # ResultadoMotor gerenciado com nome: encerrar tenta parar o container (docker ausente) sem erro
    r = osrm.ResultadoMotor(url="http://localhost:5000", modo="docker", ativo=True,
                            gerenciado=True, nome=osrm.CONTAINER_OSRM)
    osrm.encerrar(r)


def test_garantir_grafo_sem_url_e_noop(tmp_path):
    # sem graph_path e sem graph_url → nada a provisionar, devolve None (cai no público)
    assert osrm.garantir_grafo({}, tmp_path) is None

def test_garantir_grafo_usa_path_existente(tmp_path):
    g = tmp_path / "brazil-latest.osrm"
    g.write_text("x")
    assert osrm.garantir_grafo({"graph_path": str(g)}, tmp_path / "outro") == str(g)

def test_garantir_grafo_reusa_ja_provisionado(tmp_path):
    (tmp_path / "brazil-latest.osrm").write_text("x")  # já provisionado antes
    got = osrm.garantir_grafo({"graph_url": "http://exemplo/inexistente.tar.gz"}, tmp_path)
    assert got == str(tmp_path / "brazil-latest.osrm")  # não baixa; reusa

def test_base_partes_normaliza():
    assert osrm._base_partes("http://x/g.tar.gz.part") == "http://x/g.tar.gz.part"
    assert osrm._base_partes("http://x/g.tar.gz.part00") == "http://x/g.tar.gz.part"
    assert osrm._base_partes("http://x/g.tar.gz.part7") == "http://x/g.tar.gz.part"

def test_garantir_grafo_em_partes(tmp_path):
    import io, tarfile, gzip
    # cria um tar.gz com um 'brazil-latest.osrm' dentro
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        dado = b"GRAFO-OSRM-FAKE" * 5000
        info = tarfile.TarInfo("brazil-latest.osrm"); info.size = len(dado)
        t.addfile(info, io.BytesIO(dado))
    targz = gzip.compress(buf.getvalue())
    # divide em 2 partes
    meio = len(targz) // 2
    srv = tmp_path / "srv"; srv.mkdir()
    (srv / "brazil-osrm-mld.tar.gz.part00").write_bytes(targz[:meio])
    (srv / "brazil-osrm-mld.tar.gz.part01").write_bytes(targz[meio:])
    base_uri = (srv / "brazil-osrm-mld.tar.gz.part").as_uri()
    destino = tmp_path / "dl"
    got = osrm.garantir_grafo({"graph_url": base_uri}, destino)
    assert got == str(destino / "brazil-latest.osrm") and (destino / "brazil-latest.osrm").exists()

def test_baixar_partes_sem_nenhuma_parte(tmp_path):
    base = (tmp_path / "naoexiste.part").as_uri()
    assert osrm._baixar_partes(base, tmp_path / "out.tar.gz") is False
    assert not (tmp_path / "out.tar.gz").exists()

def test_garantir_grafo_nome_base_diferente(tmp_path):
    # o move deve derivar o padrão do arquivo encontrado, não de 'brazil-latest' fixo.
    import io, tarfile, gzip
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for nome in ("brasil.osrm", "brasil.osrm.edges"):
            dado = (nome + "-data").encode() * 100
            info = tarfile.TarInfo(nome); info.size = len(dado)
            t.addfile(info, io.BytesIO(dado))
    (tmp_path / "g.tar.gz").write_bytes(gzip.compress(buf.getvalue()))
    destino = tmp_path / "dl"
    got = osrm.garantir_grafo({"graph_url": (tmp_path / "g.tar.gz").as_uri()}, destino)
    assert got == str(destino / "brasil.osrm")
    assert (destino / "brasil.osrm.edges").exists()       # artefato irmão também foi movido

def test_remover_container_retorna_bool():
    assert osrm._remover_container("") is False            # nome vazio
    assert isinstance(osrm._remover_container("openrotas-osrm-x"), bool)


# -------------------------------- local_data ---------------------------------
@pytest.fixture(scope="module")
def reg():
    return local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")

def test_essenciais_presentes(reg):
    assert reg.essenciais_ok() is True

def test_municipios_carrega_e_tem_linhas(reg):
    df = reg.municipios()
    assert len(df) > 5000  # ~5.570 municípios

def test_indice_ibge_nao_vazio(reg):
    idx = reg.indice_municipios_por_ibge()
    assert len(idx) > 5000

def test_assinatura_detecta_arquivo(reg):
    a = reg.assinatura("municipios")
    assert a["existe"] and a["bytes"] > 0 and len(a["hash12"]) == 12

def test_offline_pronto_estrutura(reg):
    off = reg.offline_pronto()
    assert off["geocodificacao_hidro_local"] is True      # bases embarcadas presentes
    assert off["roteamento_local"] is False               # sem grafo OSRM local aqui
    assert off["pronto"] is False and "osrm_brasil" in " ".join(off["faltam"])

def test_osrm_brasil_e_opcional_ausente(reg):
    assert reg.existe("osrm_brasil") is False

def test_legivel_base_valida(reg):
    assert reg.legivel("municipios") is True          # parquet real abre (lê só o schema)

def test_legivel_detecta_parquet_corrompido(tmp_path):
    # um "parquet" com lixo deve ser detectado como não-legível (§18)
    r = local_data.LocalDataRegistry(cfg.app_root(), tmp_path / "data_local")
    ov = r.override_dir / "municipios.parquet"
    ov.parent.mkdir(parents=True, exist_ok=True)
    ov.write_bytes(b"isto nao e um parquet valido")
    assert r.existe("municipios") is True             # existe (override)
    assert r.legivel("municipios") is False           # mas não abre → corrompido

def test_override_vence_o_bundle(tmp_path):
    # Uma cópia reparada/atualizada no diretório de override do perfil do usuário tem
    # prioridade sobre a base embarcada read-only (§18/§19/§45).
    r = local_data.LocalDataRegistry(cfg.app_root(), tmp_path / "data_local")
    bundle = r.caminho("municipios")
    assert "data_local" not in str(bundle)          # sem override → aponta para o bundle
    ov = r.override_dir / "municipios.parquet"
    ov.parent.mkdir(parents=True, exist_ok=True)
    ov.write_text("reparado")
    assert r.caminho("municipios") == ov            # com override → vence o bundle


# ----------------------------- resource_manager ------------------------------
def test_rm_status_lista_recursos():
    linhas = rm.status()
    chaves = {r["chave"] for r in linhas}
    assert {"municipios", "osrm_brasil"} <= chaves
    mun = next(r for r in linhas if r["chave"] == "municipios")
    assert mun["instalado"] is True and mun["estado"] == rm.OK and mun["obrigatorio"] is True
    assert mun["modulo"]  # cada recurso sabe qual módulo o usa

def test_rm_osrm_opcional_ausente():
    g = next(r for r in rm.status() if r["chave"] == "osrm_brasil")
    assert g["tipo"] == "provisionável" and g["obrigatorio"] is False
    assert g["instalado"] is False and g["estado"] == rm.OPCIONAL_AUSENTE

def test_rm_verificar_essenciais_ok():
    v = rm.verificar()
    assert v["ok"] is True and v["faltam_obrigatorios"] == []

def test_rm_provisionar_sem_url_e_noop():
    r = rm.provisionar_grafo({})
    assert r["ok"] is False  # sem graph_url, nada a baixar

def test_rm_resumo_ambiente_texto():
    txt = rm.resumo_ambiente()
    assert "Recursos do software" in txt and "municipios" in txt


# ---------------------- painel (Central de Recursos — §17/§24) ---------------
def test_painel_html_tem_secoes_e_recursos():
    h = painel.construir_html()
    assert "<!doctype html>" in h and "Central de Recursos" in h
    assert "Recursos do software" in h and "Prontidão offline" in h and "Perfil de execução" in h
    assert "municipios" in h          # a tabela de recursos foi preenchida
    assert "prefers-color-scheme" in h  # tema claro/escuro

def test_painel_gera_arquivo(tmp_path):
    out = tmp_path / "central.html"
    got = painel.gerar(str(out))
    assert got == str(out) and out.exists()
    conteudo = out.read_text(encoding="utf-8")
    assert conteudo.startswith("<!doctype html>") and "</html>" in conteudo

def test_painel_escapa_conteudo_sem_quebrar():
    # construir_html nunca levanta e produz HTML bem-formado mesmo sem osrm_cfg
    h = painel.construir_html(osrm_cfg={"graph_url": "http://x/<b>"})
    assert "<html" in h and "</html>" in h


# ------------------------------- make_icon (§38) -----------------------------
def test_make_icon_gera_ico_multi_resolucao(tmp_path):
    import make_icon
    out = tmp_path / "openrotas.ico"
    got = make_icon.gerar(str(out))
    if got is None:
        pytest.skip("Pillow indisponível neste ambiente")
    assert out.exists()
    from PIL import Image
    im = Image.open(str(out))
    assert im.format == "ICO"
    assert (256, 256) in set(im.info.get("sizes", []))   # alta resolução presente

def test_rm_reparar_tudo_sem_base_url():
    # sem base_url e com as essenciais presentes: nada a baixar, verificação OK, ok=True
    rel = rm.reparar_tudo(osrm_cfg={}, base_url="")
    assert rel["verificacao"]["ok"] is True
    assert rel["bases_atualizadas"] == [] and rel["grafo"] is None and rel["ok"] is True
    assert rel["bases_reparadas"] == []

def test_rm_reparar_corrompidos_rebaixa_forcado(tmp_path, monkeypatch):
    # Uma base corrompida na MESMA versão deve ser re-baixada (forçado) da Release e auto-curar.
    import hashlib
    monkeypatch.setattr(cfg, "user_data_dir", lambda: tmp_path / "ud")   # isola do perfil real
    monkeypatch.setattr(rm, "_manifesto_local_path", lambda: tmp_path / "ml.json")
    # arquivo "bom" servido via file:// (base_url = pasta); sha256 confere.
    srv = tmp_path / "srv"; srv.mkdir()
    bom = b"PARQUET-BOM-SIMULADO" * 100
    (srv / "snirh_rios.csv").write_bytes(bom)
    base_url = srv.as_uri()
    remoto = {"recursos": {"snirh_rios": {"versao": "2026.10", "arquivo": "snirh_rios.csv",
                                          "sha256": hashlib.sha256(bom).hexdigest()}}}
    res = rm.reparar_corrompidos(remoto, base_url, ["snirh_rios"])
    assert len(res) == 1 and res[0]["chave"] == "snirh_rios" and res[0]["ok"] is True
    # o arquivo foi gravado no override do perfil do usuário
    _, reg = rm._registry()
    assert (reg.override_dir / "snirh_rios.csv").read_bytes() == bom

def test_rm_reparar_corrompidos_pula_grafo():
    res = rm.reparar_corrompidos({"recursos": {}}, "http://x/", ["osrm_brasil"])
    assert res[0]["ok"] is False and "provision" in res[0]["detalhe"].lower()

def test_rm_reparar_tudo_grafo_nao_polui_ok(monkeypatch):
    # manifesto remoto sobe só o grafo (provisionável): NÃO deve entrar em bases_atualizadas
    # nem derrubar o ok (as bases essenciais estão presentes e legíveis).
    remoto = {"recursos": {"osrm_brasil": {"versao": "2099.1", "arquivo": "brazil-osrm-mld.tar.gz"}}}
    monkeypatch.setattr(rm, "carregar_manifesto_remoto", lambda *a, **k: remoto)
    rel = rm.reparar_tudo(osrm_cfg={}, base_url="https://exemplo/dados/")
    assert rel["bases_atualizadas"] == []          # grafo excluído do atualizar
    assert rel["ok"] is True and isinstance(rel["ok"], bool)

def test_rm_reparar_tudo_manifesto_remoto_ausente_nao_quebra(monkeypatch):
    # manifesto remoto indisponível → {} → sem atualizações, não levanta, ok continua True
    monkeypatch.setattr(rm, "carregar_manifesto_remoto", lambda *a, **k: {})
    rel = rm.reparar_tudo(osrm_cfg={}, base_url="http://exemplo.invalido/x")
    assert rel["ok"] is True and rel["bases_atualizadas"] == []

def test_osrm_telemetria_nunca_quebra():
    from engines import osrm_manager as _osrm
    # helper defensivo: não deve levantar mesmo com campos arbitrários
    _osrm._telemetria("teste", ok=True, ms=1.0)

def test_launcher_tel_nunca_quebra():
    import launcher
    # helper defensivo de telemetria do launcher: não deve levantar
    launcher._tel("teste_launcher", ok=True, ms=2.0)


# ------------------------------- benchmark (§9/§29) --------------------------
def test_benchmark_exporta_json(tmp_path):
    from engines import benchmark as bm
    resultados = [{"rotulo": "OSRM local", "taxa_sucesso_pct": 100.0, "lat_media_s": 0.03},
                  {"rotulo": "OSRM público", "taxa_sucesso_pct": 90.0, "lat_media_s": 0.8}]
    out = tmp_path / "bench.json"
    assert bm.exportar_json(resultados, str(out)) is True
    import json as _json
    dados = _json.loads(out.read_text(encoding="utf-8"))
    assert "gerado_em" in dados and len(dados["resultados"]) == 2
    assert dados["resultados"][0]["rotulo"] == "OSRM local"

def test_benchmark_registrar_telemetria_nunca_quebra():
    from engines import benchmark as bm
    # não deve levantar mesmo com resultados mínimos/estranhos
    bm.registrar_telemetria([{"rotulo": "x", "sucessos": 1, "lat_media_s": 0.05}])
    bm.registrar_telemetria([{}])

def test_benchmark_carregar_pares_amostra():
    from engines import benchmark as bm
    pares = bm.carregar_pares(bm.SAMPLE)
    assert len(pares) >= 5 and len(pares[0]) == 5   # nome + 4 coords


# ---------------------- resource_manager: manifesto (§18/§19/§45) ------------
def test_rm_manifesto_embarcado_valido():
    m = rm.carregar_manifesto()
    assert m.get("schema") == 1
    rec = m.get("recursos", {})
    assert "municipios" in rec and "osrm_brasil" in rec
    assert all("versao" in r and "arquivo" in r for r in rec.values())

def test_rm_versao_maior_numerica():
    assert rm._versao_maior("2026.11", "2026.10") is True
    assert rm._versao_maior("2026.10", "2026.10") is False
    assert rm._versao_maior("2026.9", "2026.10") is False   # compara por campo, não texto

def test_rm_verificar_atualizacoes_detecta_versao_nova():
    local = {"recursos": {"municipios": {"versao": "2026.10", "arquivo": "municipios.parquet"}}}
    remoto = {"recursos": {"municipios": {"versao": "2026.11", "arquivo": "municipios.parquet",
                                          "sha256": "abc", "obrigatorio": True}}}
    pend = rm.verificar_atualizacoes(remoto, local)
    assert len(pend) == 1 and pend[0]["chave"] == "municipios"
    assert pend[0]["versao_remota"] == "2026.11" and pend[0]["obrigatorio"] is True

def test_rm_verificar_atualizacoes_sem_mudanca():
    mesmo = {"recursos": {"municipios": {"versao": "2026.10", "arquivo": "municipios.parquet"}}}
    assert rm.verificar_atualizacoes(mesmo, mesmo) == []

def test_rm_manifesto_local_overlay_idempotente(tmp_path, monkeypatch):
    # Após registrar uma versão instalada no manifesto local, carregar_manifesto() a sobrepõe
    # e verificar_atualizacoes deixa de reportar o recurso como pendente (§19, idempotência).
    local = tmp_path / "manifest.local.json"
    monkeypatch.setattr(rm, "_manifesto_local_path", lambda: local)
    rm._registrar_versao_local("municipios", "2026.11")
    m = rm.carregar_manifesto()
    assert m["recursos"]["municipios"]["versao"] == "2026.11"   # instalada vence a embarcada
    remoto = {"recursos": {"municipios": {"versao": "2026.11", "arquivo": "municipios.parquet"}}}
    assert rm.verificar_atualizacoes(remoto) == []              # nada pendente

def test_rm_atualizar_pula_grafo_osrm(tmp_path, monkeypatch):
    # osrm_brasil é provisionável (grafo), não base de cópia: atualizar NÃO deve baixá-lo.
    monkeypatch.setattr(rm, "_manifesto_local_path", lambda: tmp_path / "ml.json")
    remoto = {"recursos": {"osrm_brasil": {"versao": "2099.1", "arquivo": "brazil-osrm-mld.tar.gz"}}}
    res = rm.atualizar(remoto, "http://exemplo.invalido/base")
    assert len(res) == 1 and res[0]["chave"] == "osrm_brasil"
    assert res[0]["ok"] is False and "provision" in res[0]["detalhe"].lower()

def test_rm_baixar_e_verificar_rejeita_hash_errado(tmp_path):
    origem = tmp_path / "origem.bin"
    origem.write_bytes(b"conteudo-de-teste")
    destino = tmp_path / "destino.bin"
    r = rm.baixar_e_verificar(origem.as_uri(), destino, sha256="0" * 64)
    assert r["ok"] is False and not destino.exists()        # hash não bate → descartado

def test_rm_carregar_manifesto_remoto_via_file_url(tmp_path):
    import json as _json
    man = {"schema": 1, "recursos": {"municipios": {"versao": "2026.11", "arquivo": "municipios.parquet"}}}
    (tmp_path / "manifest.json").write_text(_json.dumps(man), encoding="utf-8")
    base_url = (tmp_path).as_uri()        # file:///.../  → + /manifest.json
    got = rm.carregar_manifesto_remoto(base_url)
    assert got.get("schema") == 1 and "municipios" in got.get("recursos", {})

def test_rm_carregar_manifesto_remoto_ausente_degrada():
    assert rm.carregar_manifesto_remoto("http://127.0.0.1:5999/naoexiste", timeout=1) == {}

def test_rm_baixar_e_verificar_aceita_hash_certo(tmp_path):
    import hashlib
    dados = b"conteudo-de-teste-ok"
    origem = tmp_path / "origem.bin"
    origem.write_bytes(dados)
    destino = tmp_path / "destino.bin"
    h = hashlib.sha256(dados).hexdigest()
    r = rm.baixar_e_verificar(origem.as_uri(), destino, sha256=h)
    assert r["ok"] is True and destino.exists() and destino.read_bytes() == dados


# ---------------------------- telemetry: exec_profile (§42) ------------------
def test_telemetria_registra_e_lista(tmp_path):
    arq = tmp_path / "t.jsonl"
    assert exec_profile.registrar({"evento": "rota", "ms": 12.0, "ok": True}, caminho=arq) is True
    evs = exec_profile.listar(10, caminho=arq)
    assert len(evs) == 1 and evs[0]["evento"] == "rota"
    assert "ts" in evs[0] and "iso" in evs[0]       # carimbo automático

def test_telemetria_cronometro_mede_e_registra(tmp_path):
    arq = tmp_path / "t.jsonl"
    with exec_profile.cronometro("lote", caminho=arq, motor="osrm_local"):
        pass
    evs = exec_profile.listar(10, caminho=arq)
    assert len(evs) == 1
    assert evs[0]["evento"] == "lote" and evs[0]["ok"] is True
    assert evs[0]["motor"] == "osrm_local" and isinstance(evs[0]["ms"], (int, float))

def test_telemetria_cronometro_registra_erro_e_relevanta(tmp_path):
    arq = tmp_path / "t.jsonl"
    with pytest.raises(ValueError):
        with exec_profile.cronometro("rota", caminho=arq):
            raise ValueError("falhou")
    evs = exec_profile.listar(10, caminho=arq)
    assert len(evs) == 1 and evs[0]["ok"] is False and "ValueError" in evs[0]["erro"]

def test_telemetria_resumo_agrega(tmp_path):
    arq = tmp_path / "t.jsonl"
    for ms in (10.0, 20.0, 30.0, 40.0):
        exec_profile.registrar({"evento": "rota", "ms": ms, "ok": True}, caminho=arq)
    exec_profile.registrar({"evento": "rota", "ms": 50.0, "ok": False}, caminho=arq)
    r = exec_profile.resumo(caminho=arq)
    assert r["total"] == 5 and r["ok"] == 4 and r["erro"] == 1
    assert r["por_evento"]["rota"] == 5
    t = r["tempos"]["rota"]
    assert t["n"] == 5 and t["max_ms"] == 50.0 and 10.0 <= t["media_ms"] <= 50.0

def test_telemetria_resumo_vazio(tmp_path):
    r = exec_profile.resumo(caminho=tmp_path / "inexistente.jsonl")
    assert r["total"] == 0 and r["por_evento"] == {} and r["tempos"] == {}

def test_telemetria_limpar(tmp_path):
    arq = tmp_path / "t.jsonl"
    exec_profile.registrar({"evento": "x"}, caminho=arq)
    assert arq.exists()
    assert exec_profile.limpar(caminho=arq) is True and not arq.exists()

def test_telemetria_nunca_levanta_em_caminho_invalido():
    # diretório inexistente/sem permissão não deve propagar exceção
    assert exec_profile.registrar({"evento": "x"}, caminho="/proc/openrotas-nao-existe/t.jsonl") is False


# -------------------------------- diagnostics --------------------------------
def test_diagnostico_essencial_ok(capsys, monkeypatch):
    monkeypatch.setenv("OPENROTAS_NO_NET", "1")   # não bate na rede durante o teste
    rc = diagnostics.executar(verbose=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "tudo essencial OK" in out
    assert "Offline:" in out and "Perfil de desempenho:" in out


# ----------------------------- app_update (§19) ------------------------------
def test_update_versao_atual_casa_com_config():
    assert app_update.versao_atual() == cfg.APP_VERSION

def test_update_comparacao_de_versao():
    assert app_update.ha_atualizacao("0.1.0", "0.2.0") is True
    assert app_update.ha_atualizacao("0.1.0", "0.1.0") is False
    assert app_update.ha_atualizacao("0.2.0", "0.1.9") is False   # por campo, não texto
    assert app_update.ha_atualizacao("v0.1.0", "v0.1.1") is True   # tolera prefixo 'v'

def test_update_verificar_offline_degrada(monkeypatch):
    # consulta indisponível → não quebra, marca disponivel=False
    monkeypatch.setattr(app_update, "consultar_release",
                        lambda *a, **k: {"ok": False, "versao": "", "tag": "", "url_instalador": None})
    v = app_update.verificar()
    assert v["disponivel"] is False and v["ha_atualizacao"] is False
    assert v["atual"] == cfg.APP_VERSION

def test_update_verificar_detecta_nova(monkeypatch):
    monkeypatch.setattr(app_update, "consultar_release",
                        lambda *a, **k: {"ok": True, "versao": "99.0.0",
                                         "url_instalador": "http://x/OpenRotas-Setup.exe", "tag": "app-latest"})
    v = app_update.verificar()
    assert v["disponivel"] is True and v["ha_atualizacao"] is True and v["remota"] == "99.0.0"

def test_update_baixar_sem_url_nao_quebra():
    r = app_update.baixar_instalador("")
    assert r["ok"] is False

def test_update_extrair_versao():
    assert app_update._extrair_versao("OpenRotas 0.2.0") == "0.2.0"
    assert app_update._extrair_versao("v1.10.3") == "1.10.3"
    assert app_update._extrair_versao("sem numero") == ""

def test_update_compara_0_10_maior_que_0_9():
    # bug clássico de comparação textual: 0.10 deve ser > 0.9
    assert app_update.ha_atualizacao("0.9", "0.10") is True


# --------------------- osrm parts: classificação de erro ---------------------
def test_osrm_parte_ausente_classifica():
    import urllib.error
    he404 = urllib.error.HTTPError("u", 404, "nf", {}, None)
    he500 = urllib.error.HTTPError("u", 500, "err", {}, None)
    assert osrm._parte_ausente(he404) is True
    assert osrm._parte_ausente(he500) is False          # 5xx = transitório, não fim
    assert osrm._parte_ausente(urllib.error.URLError(FileNotFoundError())) is True
    assert osrm._parte_ausente(urllib.error.URLError(ConnectionResetError())) is False


# ============================================================================
#  CONTEÚDO COMPLETO DO BRASIL — graph_url turnkey, provisionamento e Central
#  de Dados (a opção DENTRO do software para baixar/instalar tudo). §12/§32.
# ============================================================================

# ---- desktop_config: URL turnkey do grafo ----
def test_url_grafo_padrao_aponta_para_release():
    u = cfg.url_grafo_padrao()
    assert u.startswith("https://github.com/") and "osrm-brasil-latest" in u
    assert u.endswith("brazil-osrm-mld.tar.gz.part00")

def test_resolver_graph_url_configurado_vence():
    conf = {"osrm": {"graph_url": "http://meu/servidor/grafo.tar.gz.part00"}}
    assert cfg.resolver_graph_url(conf) == "http://meu/servidor/grafo.tar.gz.part00"

def test_resolver_graph_url_cai_no_padrao():
    assert cfg.resolver_graph_url({"osrm": {"mode": "docker"}}) == cfg.url_grafo_padrao()
    assert cfg.resolver_graph_url({}) == cfg.url_grafo_padrao()

def test_resolver_graph_url_env_override(monkeypatch):
    import importlib
    monkeypatch.setenv("OPENROTAS_REPO", "fulano/Fork")
    monkeypatch.setenv("OPENROTAS_GRAFO_TAG", "osrm-x")
    importlib.reload(cfg)
    try:
        u = cfg.url_grafo_padrao()
        assert "fulano/Fork" in u and "osrm-x" in u
    finally:
        monkeypatch.delenv("OPENROTAS_REPO", raising=False)
        monkeypatch.delenv("OPENROTAS_GRAFO_TAG", raising=False)
        importlib.reload(cfg)   # restaura os padrões para os demais testes


# ---- osrm_manager: callback de progresso no download em partes ----
def test_baixar_partes_emite_progresso(tmp_path):
    srv = tmp_path / "srv"; srv.mkdir()
    (srv / "g.tar.gz.part00").write_bytes(b"A" * (1024 * 300))
    (srv / "g.tar.gz.part01").write_bytes(b"B" * (1024 * 300))
    base = (srv / "g.tar.gz.part").as_uri()
    eventos = []
    ok = osrm._baixar_partes(base, tmp_path / "out.tar.gz", progresso=lambda ev: eventos.append(ev))
    assert ok is True and (tmp_path / "out.tar.gz").exists()
    assert any(e.get("fase") == "baixando" for e in eventos)
    assert any(e.get("parte_concluida") for e in eventos)   # fim de cada parte sinalizado

def test_baixar_partes_progresso_que_levanta_nao_quebra(tmp_path):
    srv = tmp_path / "srv"; srv.mkdir()
    (srv / "g.tar.gz.part00").write_bytes(b"A" * 2048)
    base = (srv / "g.tar.gz.part").as_uri()
    def _boom(ev):
        raise RuntimeError("callback ruim")
    # um progresso defeituoso NUNCA pode abortar/corromper o download
    assert osrm._baixar_partes(base, tmp_path / "out.tar.gz", progresso=_boom) is True

def test_garantir_grafo_emite_pronto_quando_ja_existe(tmp_path):
    destino = tmp_path / "dl"; destino.mkdir()
    (destino / "brazil-latest.osrm").write_bytes(b"x")
    eventos = []
    got = osrm.garantir_grafo({}, destino, progresso=lambda ev: eventos.append(ev))
    assert got == str(destino / "brazil-latest.osrm")
    assert any(e.get("fase") == "pronto" for e in eventos)


# ---- provisionamento: camada pura ----
def test_prov_pasta_de_dados_existe():
    p = prov.pasta_de_dados()
    assert p.name == "data_local"

def test_prov_humano_bytes():
    assert prov.humano_bytes(0) == "0 B"
    assert prov.humano_bytes(1536).endswith("KB")
    assert prov.humano_bytes(6_700_000_000).endswith("GB")
    assert prov.humano_bytes("xx") == "—"

def test_prov_inventario_estrutura():
    inv = prov.inventario()
    assert "recursos" in inv and "resumo" in inv and "offline" in inv
    assert inv["resumo"]["total"] >= 1
    # as bases essenciais estão instaladas neste repo (reassembladas) → nenhum obrigatório falta
    assert isinstance(inv["resumo"]["faltam_obrigatorios"], list)
    assert "osrm_brasil" in inv["resumo"]["faltam_opcionais"]   # grafo ausente aqui

def test_prov_grafo_instalado_falso_aqui():
    assert prov.grafo_instalado() is False

def test_prov_baixar_grafo_em_partes_para_a_pasta(tmp_path, monkeypatch):
    import io, tarfile, gzip
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        dado = b"OSRM" * 4000
        info = tarfile.TarInfo("brazil-latest.osrm"); info.size = len(dado)
        t.addfile(info, io.BytesIO(dado))
    targz = gzip.compress(buf.getvalue())
    srv = tmp_path / "srv"; srv.mkdir()
    meio = len(targz) // 2
    (srv / "brazil-osrm-mld.tar.gz.part00").write_bytes(targz[:meio])
    (srv / "brazil-osrm-mld.tar.gz.part01").write_bytes(targz[meio:])
    base = (srv / "brazil-osrm-mld.tar.gz.part").as_uri()
    destino = tmp_path / "pasta_dados"
    monkeypatch.setattr(prov, "pasta_de_dados", lambda: destino)
    eventos = []
    r = prov.baixar_grafo(progresso=lambda ev: eventos.append(ev),
                          conf={"osrm": {"graph_url": base}})
    assert r["ok"] is True and (destino / "brazil-latest.osrm").exists()
    assert any(e.get("fase") in ("baixando", "extraindo") for e in eventos)

def test_prov_baixar_grafo_sem_url_nao_quebra(monkeypatch):
    # força graph_url vazio e sem padrão → mensagem clara, sem levantar
    monkeypatch.setattr(cfg, "resolver_graph_url", lambda *a, **k: "")
    r = prov.baixar_grafo(conf={"osrm": {}})
    assert r["ok"] is False and "nada a baixar" in r["detalhe"]

def test_prov_abrir_pasta_headless_e_noop(monkeypatch):
    monkeypatch.setenv("OPENROTAS_NO_NET", "1")
    assert prov.abrir_pasta_dados() is False      # em CI/headless não tenta abrir GUI

def test_prov_ativar_roteamento_local_grava_config(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "user_data_dir", lambda: tmp_path / "ud")
    r = prov.ativar_roteamento_local()
    assert r["ok"] is True
    import json as _json
    conf = _json.loads((tmp_path / "ud" / "config" / "desktop.json").read_text(encoding="utf-8"))
    assert conf["osrm"]["mode"] == "docker"
    assert conf["osrm"]["graph_url"].endswith("part00")   # garante uma URL utilizável

def test_prov_ativar_roteamento_local_preserva_config(tmp_path, monkeypatch):
    import json as _json
    ud = tmp_path / "ud"; (ud / "config").mkdir(parents=True)
    (ud / "config" / "desktop.json").write_text(
        _json.dumps({"SUPABASE_URL": "https://x", "osrm": {"graph_url": "http://meu/g.part00"}}),
        encoding="utf-8")
    monkeypatch.setattr(cfg, "user_data_dir", lambda: ud)
    prov.ativar_roteamento_local()
    conf = _json.loads((ud / "config" / "desktop.json").read_text(encoding="utf-8"))
    assert conf["SUPABASE_URL"] == "https://x"               # resto preservado
    assert conf["osrm"]["mode"] == "docker"
    assert conf["osrm"]["graph_url"] == "http://meu/g.part00"  # url do usuário preservada

def test_prov_reparar_bases_emite_e_nao_quebra():
    eventos = []
    rel = prov.reparar_bases(progresso=lambda ev: eventos.append(ev))
    assert isinstance(rel, dict)
    assert any(e.get("fase") == "concluido" for e in eventos)


# ---- central_dados: fallback de texto (sem GUI) ----
def test_central_resumo_texto_tem_pasta_e_grafo():
    txt = central_dados._resumo_texto()
    assert "Central de Dados" in txt and "grafo" in txt.lower()
    assert "Pasta de dados:" in txt

def test_central_executar_texto_sem_baixar_retorna_0(capsys):
    rc = central_dados._executar_texto(baixar=False)
    assert rc == 0
    assert "--central --baixar" in capsys.readouterr().out

def test_central_main_cai_para_texto_sem_display(monkeypatch, capsys):
    # sem Tkinter utilizável, main() usa o modo texto e não levanta
    monkeypatch.setattr(central_dados, "_tkinter_disponivel", lambda: False)
    rc = central_dados.main([])
    assert rc == 0 and "Central de Dados" in capsys.readouterr().out


# ---- manifesto: completude (todas as camadas nacionais embarcadas) ----
def test_manifesto_cobre_catalogo_completo():
    m = rm.carregar_manifesto()
    rec = m.get("recursos", {})
    for chave in ("drenagem", "rodovias", "ferrovias", "pontes", "travessias", "hidrovias",
                  "eclusas", "atracadouros_terminal", "complexos_portuarios", "sinalizacao"):
        assert chave in rec, "manifesto deveria listar %r" % chave
    assert rec["drenagem"]["obrigatorio"] is True and rec["rodovias"]["obrigatorio"] is True

def test_painel_tem_bloco_dados_completos():
    h = painel.construir_html()
    assert "Dados completos" in h and "Central de Dados" in h


# ============================================================================
#  AUDITOR DE COBERTURA NACIONAL (§3/§4/§40/§42/§64/§65/§66) — prova objetiva,
#  números derivados dos dados REAIS instalados (nunca fabricados).
# ============================================================================

def test_uf_do_geocodigo_mapeia_prefixo():
    import pandas as pd
    s = pd.Series(["3550308", "1100015", "5300108", "2927408", "abc", "9999999"])
    uf = list(ca._uf_do_geocodigo(s))
    assert uf[0] == "SP" and uf[1] == "RO" and uf[2] == "DF" and uf[3] == "BA"
    assert pd.isna(uf[4]) and pd.isna(uf[5])      # lixo/código inexistente → NaN (sem inventar)

def test_auditoria_estados_27_e_municipios_reais():
    reg = ca._registry()
    em = ca.cobertura_estados_municipios(reg)
    assert em["estados"]["encontrado"] == 27 and em["estados"]["status"] == "OK"
    assert set(em["estados"]["presentes"]) == ca.UFS_ESPERADAS
    # número REAL de municípios (IBGE 5.570 + Fernando de Noronha) — não um valor inventado
    assert em["municipios"]["encontrado"] >= ca.MUNICIPIOS_OFICIAIS
    assert len(em["municipios"]["por_uf"]) == 27

def test_auditoria_completa_estrutura_e_camadas():
    laudo = ca.auditar(rapido=True)
    assert laudo["estados"]["encontrado"] == 27
    assert "rodovias" in laudo["camadas"] and "drenagem" in laudo["camadas"]
    rod = laudo["camadas"]["rodovias"]
    assert rod["instalado"] is True and rod["feicoes"] > 100000
    assert len(rod["ufs_presentes"]) >= 20          # malha nacional presente em (quase) todas as UFs
    assert rod["status"] in ("OK", "PARCIAL")
    r = laudo["resumo"]
    assert r["dimensoes"] == r["ok"] + r["parciais"] + r["ausentes"]

def test_auditoria_grafo_ausente_e_honesto():
    # o grafo OSRM não está instalado neste ambiente → AUSENTE (não mascarado como OK)
    laudo = ca.auditar(rapido=True)
    assert laudo["grafo"]["instalado"] is False and laudo["grafo"]["status"] == "AUSENTE"

def test_auditoria_presenca_uf_camada_ausente(tmp_path):
    # registry isolado sem bases → camada não instalada vira AUSENTE, sem levantar
    import local_data
    reg = local_data.LocalDataRegistry(cfg.app_root(), tmp_path / "data_local")
    r = ca.presenca_espacial_uf(reg, "eclusas", {}, amostra=None)
    # eclusas é embarcada (existe no bundle), mas sem bboxes a presença fica vazia, sem quebrar
    assert isinstance(r["ufs_presentes"], list)

def test_render_texto_tem_cabecalho_e_barra():
    laudo = ca.auditar(rapido=True)
    txt = ca.render_texto(laudo)
    assert "AUDITORIA NACIONAL" in txt and "Estados (UFs)" in txt
    assert "Municípios" in txt and "█" in txt       # barra de progresso ASCII

def test_relatorio_md_gera_arquivo(tmp_path):
    laudo = ca.auditar(rapido=True)
    out = tmp_path / "rel.md"
    got = ca.gerar_relatorio_md(laudo, out)
    assert got == str(out) and out.exists()
    conteudo = out.read_text(encoding="utf-8")
    assert conteudo.startswith("# Relatório de Cobertura Nacional")
    assert "Municípios por UF" in conteudo and "Nenhum dado foi" in conteudo  # nota de honestidade
    assert "| SP |" in conteudo                      # tabela por UF preenchida com dado real

def test_resumo_curto_e_cli():
    laudo = ca.auditar(rapido=True)
    s = ca.resumo_curto(laudo)
    assert "UFs 27/27" in s
    assert ca._cli(["--rapido"]) == 0                # essenciais presentes → saída 0

def test_painel_tem_bloco_cobertura():
    h = painel.construir_html()
    assert "Auditoria de Cobertura Nacional" in h and "Estados (UFs)" in h


# ============================================================================
#  GeoIntelligenceRepository + multimodal/fluvial (§6/§8/§24/§25) — consultas
#  espaciais unificadas (nível bbox, numpy), sobre os dados REAIS instalados.
# ============================================================================
@pytest.fixture(scope="module")
def repo():
    return georepo.GeoIntelligenceRepository()

def test_repo_arrays_projecao_leve(repo):
    a = repo.arrays("rodovias")
    assert a and a["n"] > 100000
    assert set(("lon", "lat", "xmin", "ymin", "xmax", "ymax")).issubset(a.keys())

def test_repo_camada_inexistente_degrada(repo):
    assert repo.arrays("nao_existe_xyz") is None
    assert repo.disponivel("osrm_brasil") is False      # provisionável, ausente aqui

def test_repo_intersecta_bbox_sp(repo):
    import numpy as np
    # janela sobre a cidade de São Paulo deve conter feições rodoviárias
    idx = repo.intersecta_bbox("rodovias", -46.8, -23.8, -46.3, -23.4)
    assert isinstance(idx, np.ndarray) and idx.size > 0

def test_repo_intersecta_bbox_fora_do_brasil_vazio(repo):
    # no meio do Atlântico não há feições rodoviárias
    assert repo.intersecta_bbox("rodovias", 10.0, 10.0, 11.0, 11.0).size == 0

def test_repo_proximidade_ponto(repo):
    r = repo.proximidade("drenagem", -60.02, -3.1, raio_km=25)   # Manaus/AM (muitos rios)
    assert r["total"] > 0 and r["raio_km"] == 25

def test_repo_contar_na_rota_sp_rio(repo):
    coords = [(-46.63, -23.55), (-43.20, -22.90)]
    res = repo.contar_na_rota(coords, camadas=["drenagem", "rodovias", "pontes"])
    assert res["drenagem"]["feicoes"] > 0 and res["drenagem"]["disponivel"] is True
    assert res["rodovias"]["feicoes"] > 0

def test_repo_contar_na_rota_camada_ausente(repo):
    res = repo.contar_na_rota([(-46.6, -23.5), (-46.5, -23.4)], camadas=["osrm_brasil"])
    assert res["osrm_brasil"] == {"feicoes": 0, "disponivel": False}

def test_repo_inventario_multimodal(repo):
    inv = repo.inventario_multimodal()
    assert inv["camadas"]["rodovias"]["instalado"] is True
    assert inv["camadas"]["drenagem"]["classe"] == "fluvial"
    assert "rodoviario" in inv["classes_presentes"] and "fluvial" in inv["classes_presentes"]
    assert inv["total_feicoes"] > 2_000_000

def test_repo_analise_multimodal_rota(repo):
    res = repo.analise_multimodal_rota([(-46.63, -23.55), (-43.20, -22.90)])
    assert res["cruza_rio"] is True
    assert res["por_classe"]["rodoviario"] > 0 and res["por_classe"]["fluvial"] > 0
    assert "aproximada" in res["nota"]

def test_repo_render_e_cli():
    inv = georepo.GeoIntelligenceRepository().inventario_multimodal()
    txt = georepo.render_inventario(inv)
    assert "INVENTÁRIO MULTIMODAL" in txt and "rodovias" in txt
    assert georepo._cli([]) == 0


# ============================================================================
#  TESTE NACIONAL DE ROTAS / COBERTURA DISTRIBUÍDA (§42/§43/§44/§45) — corredores
#  inter-UF nas 5 regiões, sobre os dados REAIS, pegando buracos regionais.
# ============================================================================
def test_rotas_corredores_cobrem_as_regioes():
    from audit import route_coverage as rc
    regioes = " ".join(r for *_, r in rc.CORREDORES)
    assert "Norte" in regioes and "Nordeste" in regioes and "Sul" in regioes
    assert len(rc.CORREDORES) >= 10

def test_rotas_nacional_todos_corredores_com_malha():
    from audit import route_coverage as rc
    aud = rc.auditar_rotas()
    assert aud["resumo"]["total"] == len(rc.CORREDORES)
    # toda a malha nacional deve aparecer em TODOS os corredores inter-UF (sem buraco regional)
    assert aud["resumo"]["status"] == "OK" and aud["resumo"]["ok"] == aud["resumo"]["total"]
    for c in aud["corredores"]:
        assert c["ok"] is True and c["rodoviario"] > 0

def test_rotas_amazonia_tem_rios():
    # corredores amazônicos devem cruzar muitos rios (sanidade regional — §45)
    from audit import route_coverage as rc
    aud = rc.auditar_rotas()
    amaz = [c for c in aud["corredores"] if c["corredor"].startswith(("AC→AM", "RR→PA"))]
    assert amaz and all(c["cruza_rio"] and c["fluvial"] > 0 for c in amaz)

def test_rotas_render_e_cli():
    from audit import route_coverage as rc
    aud = rc.auditar_rotas()
    txt = rc.render_texto(aud)
    assert "TESTE NACIONAL DE ROTAS" in txt and "corredores" in txt
    assert rc._cli() == 0
