# -*- coding: utf-8 -*-
"""OpenRotas Desktop — LAUNCHER (bootstrapper do software de desktop).

Fluxo:
  1. prepara diretórios persistentes do usuário + secrets.toml local + variáveis de ambiente;
  2. sobe o servidor Streamlit embutido (o MESMO streamlit_app.py da web) em 127.0.0.1:PORTA,
     numa thread, headless;
  3. espera a porta aceitar conexão;
  4. abre uma JANELA NATIVA (pywebview) apontando para o app local — com fallback para o
     navegador padrão se o pywebview não estiver disponível;
  5. ao fechar a janela, encerra o processo.

Arquitetura escolhida (Opção B do pedido): Streamlit local + launcher desktop. Reutiliza a
aplicação web inteira (ZERO perda de funcionalidade, §21/§44) e ganha as vantagens locais via
configuração (motor local, cache persistente, mais workers). Rodar localmente num IP residencial
já restaura a velocidade e a participação do Google — o maior ganho isolado.

Defensivo: cada etapa isola exceções e registra em log; nunca deixa um erro silencioso travar
o usuário sem explicação.
"""
from __future__ import annotations

import os
import sys
import time
import socket
import logging
import threading

# Garante que 'desktop/app' (módulos soltos: desktop_config/diagnostics) E 'desktop/' (pacote
# 'engines') estejam no path, tanto rodando como script solto quanto empacotado.
_AQUI = os.path.dirname(os.path.abspath(__file__))        # .../desktop/app
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))                # .../desktop  (para 'import engines...')

import desktop_config as cfg  # noqa: E402


def _configurar_logs(paths) -> None:
    log_file = paths["logs"] / "openrotas-desktop.log"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers)


log = logging.getLogger("openrotas.desktop.launcher")


def _tel(evento: str, **campos) -> None:
    """Registra um evento no perfil de execução local (§42), se disponível. Import defensivo;
    nunca quebra o launcher."""
    try:
        _t = os.path.join(os.path.dirname(_AQUI), "telemetry")
        if _t not in sys.path:
            sys.path.insert(0, _t)
        import exec_profile
        exec_profile.registrar(dict(campos, evento=evento, tipo="launcher"))
    except Exception:
        pass


def _porta_aberta(host: str, porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, porta)) == 0


def _esperar_porta(host: str, porta: int, timeout_s: float = 90.0) -> bool:
    """Espera o Streamlit subir (a 1ª inicialização carrega as bases do Brasil e pode
    demorar). Devolve True quando a porta aceita conexão; False se estourar o tempo."""
    inicio = time.time()
    while time.time() - inicio < timeout_s:
        if _porta_aberta(host, porta):
            return True
        time.sleep(0.4)
    return False


def _iniciar_streamlit(env: dict) -> None:
    """Sobe o Streamlit no processo atual (thread dedicada), chamando a CLI dele
    programaticamente — padrão que funciona tanto em DEV quanto empacotado."""
    # Aplica as variáveis de ambiente preparadas (headless/porta/cache) ANTES de importar a CLI.
    os.environ.update(env)
    app_path = str(cfg.app_root() / "streamlit_app.py")
    log.info("Subindo Streamlit: %s (porta %s)", app_path, cfg.PORTA_LOCAL)
    try:
        from streamlit.web import bootstrap as st_bootstrap
        # bootstrap.run é a API interna estável usada por 'streamlit run'.
        flag_options = {
            "server.port": cfg.PORTA_LOCAL,
            "server.address": "127.0.0.1",
            "server.headless": True,
            "browser.gatherUsageStats": False,
            "global.developmentMode": False,
        }
        st_bootstrap.run(app_path, is_hello=False, args=[], flag_options=flag_options)
    except Exception:
        log.exception("bootstrap.run falhou; tentando a CLI (stcli.main).")
        try:
            from streamlit.web import cli as stcli
            sys.argv = ["streamlit", "run", app_path,
                        "--server.port", str(cfg.PORTA_LOCAL),
                        "--server.address", "127.0.0.1",
                        "--server.headless", "true",
                        "--browser.gatherUsageStats", "false"]
            stcli.main()
        except Exception:
            log.exception("Falha fatal ao iniciar o Streamlit.")
            raise


def _abrir_janela(url: str) -> bool:
    """Abre a janela nativa (pywebview). Retorna True se abriu em modo nativo;
    False se o pywebview não está disponível (o chamador cai pro navegador)."""
    try:
        import webview  # pywebview
    except Exception:
        log.warning("pywebview indisponível — abrindo no navegador padrão.")
        return False
    try:
        webview.create_window(
            "OpenRotas — Motor Nacional de Inteligência Logística",
            url, width=1400, height=900, min_size=(1024, 700),
            text_select=True, confirm_close=True,
        )
        # Bloqueia até a janela fechar. http_server=False pois já temos nosso servidor.
        webview.start()
        return True
    except Exception:
        log.exception("pywebview falhou ao abrir — caindo pro navegador.")
        return False


def _verificar_atualizacoes(aplicar: bool = False) -> int:
    """Central de Atualizações (§17/§19): checa a versão do APP e das BASES de dados e, se
    `aplicar`, baixa o que estiver pendente (bases verificadas por sha256; instalador do app
    para o usuário rodar). Tudo best-effort e offline-safe: nada aqui derruba o software."""
    print("OpenRotas — Central de Atualizações")
    print("=" * 48)
    # 1) Aplicativo
    try:
        import app_update
        up = app_update.verificar()
        print("Aplicativo: instalada %s" % up["atual"])
        if not up["disponivel"]:
            print("  (verificação indisponível agora — offline ou sem Release publicada)")
        elif up["ha_atualizacao"]:
            print("  → NOVA versão %s disponível." % up["remota"])
            if up["url_instalador"]:
                print("    instalador: %s" % up["url_instalador"])
                if aplicar:
                    r = app_update.baixar_instalador(up["url_instalador"])
                    print("    %s" % ("baixado em %s (rode-o para atualizar)" % r["caminho"]
                                      if r["ok"] else "falha ao baixar: %s" % r["detalhe"]))
        else:
            print("  → você está na versão mais recente.")
    except Exception:
        log.warning("Checagem de atualização do app falhou.", exc_info=True)

    # 2) Bases de dados (reparo/atualização sem reinstalar — §18/§19/§45)
    try:
        from resources import resource_manager as rm
        conf = cfg.carregar_config_usuario() or {}
        base_url = str(conf.get("dados_base_url", "") or "").strip()
        print("\nBases de dados:")
        if not base_url:
            print("  (sem 'dados_base_url' no desktop.json — configure a pasta de download da")
            print("   Release de dados para habilitar reparo/atualização sem reinstalar)")
        else:
            remoto = rm.carregar_manifesto_remoto(base_url)
            if not remoto:
                print("  (manifesto remoto indisponível em %s)" % base_url)
            else:
                pend = rm.verificar_atualizacoes(remoto)
                if not pend:
                    print("  → todas as bases estão atualizadas.")
                else:
                    print("  → %d base(s) a atualizar: %s" % (len(pend), ", ".join(p["chave"] for p in pend)))
                    if aplicar:
                        for res in rm.atualizar(remoto, base_url):
                            print("    %s %s (%s)" % ("✓" if res["ok"] else "✗", res["chave"], res["detalhe"]))
    except Exception:
        log.warning("Checagem de atualização das bases falhou.", exc_info=True)
    return 0


_AJUDA = """OpenRotas Desktop — uso:
  OpenRotas.exe                 abre o aplicativo (janela nativa)
  OpenRotas.exe --diagnostico   autodiagnóstico (bases, cache, motor, offline, atualização)
  OpenRotas.exe --recursos      status dos recursos (Gerenciador de Recursos)
  OpenRotas.exe --recursos --html   abre a Central de Recursos (painel visual) no navegador
  OpenRotas.exe --atualizar     verifica atualização do app e das bases
  OpenRotas.exe --atualizar --baixar   aplica as atualizações pendentes (baixa/verifica)
  OpenRotas.exe --reparar       repara/atualiza tudo que puder, sem reinstalar (§18)
  OpenRotas.exe --help          esta ajuda
Flags auxiliares: --silencioso (diagnóstico sem imprimir)."""


def _reparar() -> int:
    """Reparo de um clique (§18): verifica e conserta o que der (bases/grafo) sem reinstalar."""
    from resources import resource_manager as rm
    conf = cfg.carregar_config_usuario() or {}
    rel = rm.reparar_tudo(osrm_cfg=conf.get("osrm"), base_url=str(conf.get("dados_base_url", "") or ""))
    print("OpenRotas — Reparo/Atualização")
    print("=" * 48)
    v = rel["verificacao"]
    print("Integridade: %s" % ("OK" if v["ok"] else "problemas"))
    if v["faltam_obrigatorios"]:
        print("  faltam (obrigatórios, exigem reinstalar): %s" % ", ".join(v["faltam_obrigatorios"]))
    for p in v["problemas"]:
        print("  corrompido (exige reinstalar): %s" % p["chave"])
    for b in rel["bases_atualizadas"]:
        print("  base %s: %s (%s)" % (b["chave"], "✓" if b["ok"] else "✗", b.get("detalhe", "")))
    if rel["grafo"] is not None:
        print("  grafo: %s (%s)" % ("✓" if rel["grafo"]["ok"] else "✗", rel["grafo"].get("detalhe", "")))
    print("\nResultado: %s" % ("tudo OK ✓" if rel["ok"] else "pendências acima"))
    return 0 if rel["ok"] else 1


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(_AJUDA)
        return 0
    paths = cfg.ensure_user_dirs()
    _configurar_logs(paths)

    # Modo DIAGNÓSTICO (usado pelo instalador no teste de integridade e pelo atalho
    # "Diagnóstico"): o MESMO executável roda o autodiagnóstico e sai, sem abrir a janela.
    if "--diagnostico" in sys.argv:
        import diagnostics
        return diagnostics.executar(verbose=("--silencioso" not in sys.argv))

    # Modo RECURSOS: Gerenciador de Recursos. Texto no terminal; com --html gera e abre a
    # Central de Recursos (painel visual) no navegador.
    if "--recursos" in sys.argv:
        _oc = (cfg.carregar_config_usuario() or {}).get("osrm")
        if "--html" in sys.argv:
            from resources import painel
            destino = paths["cache"] / "central_recursos.html"
            gerado = painel.gerar(destino, _oc)
            if gerado:
                print("Central de Recursos: %s" % gerado)
                try:
                    import webbrowser
                    from pathlib import Path as _P
                    webbrowser.open(_P(gerado).as_uri())   # file:/// válido em Windows e Unix
                except Exception:
                    pass
                return 0
            print("Falha ao gerar o painel; mostrando o resumo em texto.")
        from resources import resource_manager as rm
        print(rm.resumo_ambiente(_oc))
        return 0

    # Modo ATUALIZAR (§17/§19): verifica atualização do APP e das BASES (sem reinstalar) e sai.
    # Com --baixar, aplica o que puder (baixa bases pendentes e/ou o instalador do app).
    if "--atualizar" in sys.argv:
        return _verificar_atualizacoes(aplicar=("--baixar" in sys.argv))

    # Modo REPARAR (§18): verifica e conserta tudo que puder (bases/grafo) sem reinstalar, e sai.
    if "--reparar" in sys.argv:
        return _reparar()

    _t_inicio = time.perf_counter()
    log.info("OpenRotas Desktop iniciando. Config: %s", cfg.resumo_config())

    # [MOTOR LOCAL - Etapa 3] Garante um OSRM local (detecta/sobe/valida) conforme a config e
    # injeta a URL dele como OSRM_URL — assim o MESMO cliente de rotas da app usa o motor local.
    # Defensivo: qualquer falha → mantém o OSRM_URL atual/público (zero regressão).
    motor = None
    try:
        import engines.osrm_manager as osrm  # desktop/engines (mesmo diretório-pai no path)
        _conf = cfg.carregar_config_usuario()
        _osrm_cfg = dict(_conf.get("osrm") or {})
        # [GRAFO COMO PRODUTO] No modo docker, garante o grafo do Brasil localmente (usa o já
        # instalado; senão baixa uma vez de graph_url para o perfil do usuário). Injeta o caminho
        # resolvido em graph_path. Sem url/sem docker → no-op (cai no público). Defensivo.
        if str(_osrm_cfg.get("mode", "")).lower() == "docker":
            try:
                # 1º: grafo EMBUTIDO no bundle (instalador com embed_graph) em app_root/data_local.
                if not _osrm_cfg.get("graph_path"):
                    _dl_app = cfg.app_root() / "data_local"
                    _emb = next(_dl_app.glob("*.osrm"), None) if _dl_app.exists() else None
                    if _emb is not None:
                        _osrm_cfg["graph_path"] = str(_emb)
                        log.info("[OSRM] grafo embutido no bundle: %s", _emb)
                # 2º: senão, usa/baixa para o perfil do usuário (auto-provisionamento).
                _gp = osrm.garantir_grafo(_osrm_cfg, paths["data_local"])
                if _gp:
                    _osrm_cfg["graph_path"] = _gp
            except Exception:
                log.warning("[OSRM] provisionamento do grafo falhou; seguindo.", exc_info=True)
        motor = osrm.resolver(_osrm_cfg, osrm_url_legado=_conf.get("OSRM_URL", "") or "")
        if motor.url:
            os.environ["OSRM_URL"] = motor.url   # preparar_secrets_e_env (abaixo) grava no secrets.toml
        log.info("[OSRM] modo=%s ativo=%s url=%s (%s)", motor.modo, motor.ativo, motor.url, motor.detalhe)
    except Exception:
        log.warning("[OSRM] gerenciamento do motor local falhou; usando OSRM público.", exc_info=True)

    # [OFFLINE - Etapa 4] Sinaliza modo offline por ENV (desktop-only; o app não é alterado).
    # Offline real = motor local + bases embarcadas (geocodificação/hidro já são locais); o
    # scraper do Google simplesmente falha e o fluxo cai no motor local, como já trata hoje.
    # [LOGIN LOCAL] Em modo offline OU login local explícito, liga o bypass de login do portão
    # de auth (OPENROTAS_DESKTOP_LOCAL) — opt-in; sem internet não há como validar no Supabase.
    try:
        _conf_off = cfg.carregar_config_usuario() or {}
        _offline = bool(_conf_off.get("offline"))
        _login_local = bool(_conf_off.get("local_login")) or _offline
        if _offline:
            os.environ["OPENROTAS_OFFLINE"] = "1"
            log.info("[OFFLINE] modo offline sinalizado (OPENROTAS_OFFLINE=1).")
        if _login_local:
            os.environ["OPENROTAS_DESKTOP_LOCAL"] = "1"
            log.info("[LOGIN LOCAL] bypass de login local ligado (OPENROTAS_DESKTOP_LOCAL=1).")
    except Exception:
        pass

    import atexit
    if motor is not None:
        atexit.register(lambda: __import__("engines.osrm_manager", fromlist=["encerrar"]).encerrar(motor))

    env = cfg.preparar_secrets_e_env(paths)

    host, porta = "127.0.0.1", cfg.PORTA_LOCAL
    if _porta_aberta(host, porta):
        log.info("Já havia algo na porta %s — reaproveitando (app já aberto?).", porta)
    else:
        t = threading.Thread(target=_iniciar_streamlit, args=(env,), daemon=True)
        t.start()
        if not _esperar_porta(host, porta):
            log.error("Streamlit não respondeu a tempo na porta %s.", porta)
            print("ERRO: o motor não subiu a tempo. Veja o log em:", paths["logs"])
            return 2

    url = "http://%s:%s" % (host, porta)
    log.info("App no ar em %s", url)

    # Perfil de execução (§42): tempo até o app ficar pronto + modo do motor. Alimenta o
    # resumo do Diagnóstico com dados reais de uso. Best-effort, nunca quebra.
    try:
        _hw = cfg.detectar_hardware()
        _tel("app_pronto", ms=round((time.perf_counter() - _t_inicio) * 1000.0, 1), ok=True,
             motor=(motor.modo if motor is not None else "off"),
             motor_ativo=bool(motor.ativo) if motor is not None else False,
             perfil=_hw.get("perfil"))
    except Exception:
        pass

    if not _abrir_janela(url):
        import webbrowser
        webbrowser.open(url)
        # Sem janela nativa: mantém o processo vivo enquanto o servidor roda.
        print("OpenRotas rodando em", url, "— feche esta janela de terminal para encerrar.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
