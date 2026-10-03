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


def main() -> int:
    paths = cfg.ensure_user_dirs()
    _configurar_logs(paths)

    # Modo DIAGNÓSTICO (usado pelo instalador no teste de integridade e pelo atalho
    # "Diagnóstico"): o MESMO executável roda o autodiagnóstico e sai, sem abrir a janela.
    if "--diagnostico" in sys.argv:
        import diagnostics
        return diagnostics.executar(verbose=("--silencioso" not in sys.argv))

    log.info("OpenRotas Desktop iniciando. Config: %s", cfg.resumo_config())

    # [MOTOR LOCAL - Etapa 3] Garante um OSRM local (detecta/sobe/valida) conforme a config e
    # injeta a URL dele como OSRM_URL — assim o MESMO cliente de rotas da app usa o motor local.
    # Defensivo: qualquer falha → mantém o OSRM_URL atual/público (zero regressão).
    motor = None
    try:
        import engines.osrm_manager as osrm  # desktop/engines (mesmo diretório-pai no path)
        _conf = cfg.carregar_config_usuario()
        motor = osrm.resolver(_conf.get("osrm"), osrm_url_legado=_conf.get("OSRM_URL", "") or "")
        if motor.url:
            os.environ["OSRM_URL"] = motor.url   # preparar_secrets_e_env (abaixo) grava no secrets.toml
        log.info("[OSRM] modo=%s ativo=%s url=%s (%s)", motor.modo, motor.ativo, motor.url, motor.detalhe)
    except Exception:
        log.warning("[OSRM] gerenciamento do motor local falhou; usando OSRM público.", exc_info=True)

    # [OFFLINE - Etapa 4] Sinaliza modo offline por ENV (desktop-only; o app não é alterado).
    # Offline real = motor local + bases embarcadas (geocodificação/hidro já são locais); o
    # scraper do Google simplesmente falha e o fluxo cai no motor local, como já trata hoje.
    try:
        if (cfg.carregar_config_usuario() or {}).get("offline"):
            os.environ["OPENROTAS_OFFLINE"] = "1"
            log.info("[OFFLINE] modo offline sinalizado (OPENROTAS_OFFLINE=1).")
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
