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

import desktop_config as cfg          # noqa: E402
import diagnostics                    # noqa: E402
from engines import osrm_manager as osrm   # noqa: E402
import local_data                     # noqa: E402
from resources import resource_manager as rm   # noqa: E402
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

def test_user_data_dir_e_resumo():
    paths = cfg.ensure_user_dirs()
    assert paths["cache"].exists()
    r = cfg.resumo_config()
    assert {"app_root", "hardware", "porta", "user_data"} <= set(r)


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

def test_rm_reparar_tudo_sem_base_url():
    # sem base_url e com as essenciais presentes: nada a baixar, verificação OK, ok=True
    rel = rm.reparar_tudo(osrm_cfg={}, base_url="")
    assert rel["verificacao"]["ok"] is True
    assert rel["bases_atualizadas"] == [] and rel["grafo"] is None and rel["ok"] is True

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
