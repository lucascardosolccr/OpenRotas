# -*- coding: utf-8 -*-
"""OpenRotas Desktop — JANELA NATIVA com Chromium EMBARCADO (PySide6 / QtWebEngine).

Por que isto existe
-------------------
A primeira arquitetura abria a janela com pywebview, que no Windows depende do runtime
externo "WebView2". Quando esse runtime não está presente (ou falha), o app caía no
navegador e aparecia um "localhost que não funciona". Aqui o motor de renderização
(Chromium) vem DENTRO do próprio executável, via QtWebEngine — então a janela nativa
abre SEM depender de nada instalado no Windows: nada de navegador, nada de localhost solto.

A aplicação inteira (o MESMO streamlit_app.py) roda DENTRO desta janela. Além de confiável,
a janela é mais bonita e moderna que a web: uma tela de abertura (splash) com a marca
enquanto o motor sobe, a barra/menu do Streamlit escondida (cara de app, não de página), e
uma camada de tema PREMIUM injetada só no desktop (tipografia nítida, scrollbars finas da
marca, brilho ambiente) — sem tocar numa linha do app web.

Este módulo é defensivo: `disponivel()` diz se o QtWebEngine está presente; `abrir()` nunca
levanta para o chamador (devolve False se não conseguir), para o launcher poder cair no
pywebview e, por último, no navegador. As funções puras `_css_premium()` e `_html_splash()`
são testáveis sem display.
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger("openrotas.desktop.janela")

# Identidade visual (espelha os tokens do app web — streamlit_app.py / .streamlit/config.toml).
MARCA = {
    "bg0": "#0B0F1A",       # fundo mais profundo que a web (#0E1117) — dá sensação premium no app
    "bg1": "#0E1117",
    "bg2": "#1E232F",
    "borda": "#2D3342",
    "brand": "#3B82F6",
    "brand2": "#60A5FA",
    "texto": "#F9FAFB",
    "texto2": "#9AA4B2",
}

TITULO = "OpenRotas — Motor Nacional de Inteligência Logística"


def disponivel() -> bool:
    """True se o QtWebEngine (Chromium embarcado) pode ser importado neste ambiente."""
    try:
        import PySide6  # noqa: F401
        from PySide6 import QtWebEngineWidgets  # noqa: F401
        return True
    except Exception:
        return False


def _aplicar_tokens(texto: str) -> str:
    """Substitui @TOKEN@ pelos valores da MARCA. Usamos replacement de token (não %-format
    nem str.format) porque CSS/HTML têm muitos '%' e '{}' literais que quebrariam aqueles."""
    for chave, valor in MARCA.items():
        texto = texto.replace("@%s@" % chave.upper(), valor)
    return texto


def _css_premium() -> str:
    """Camada de tema PREMIUM injetada só no desktop (additiva, não refaz o design da web).
    Ganhos que fazem parecer um app nativo de alto padrão: tipografia nítida, scrollbars
    finas da marca, seleção com a cor da marca, brilho ambiente no fundo, e a barra/menu do
    Streamlit escondida (sem "Deploy"/hambúrguer — cara de software, não de site)."""
    return _aplicar_tokens("""
    /* OpenRotas Desktop — camada premium (injetada pela janela nativa) */
    html, body, .stApp {
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
    }
    /* Cara de APP: esconde a barra/menu/rodapé do Streamlit (não há "Deploy" num desktop). */
    #MainMenu, header[data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="stStatusWidget"], [data-testid="stDecoration"], footer {
        display: none !important;
        visibility: hidden !important;
    }
    .stApp > header { height: 0 !important; }
    .block-container { padding-top: 2.2rem !important; }
    /* Brilho ambiente suave no fundo — profundidade que a web não tem. */
    .stApp {
        background:
          radial-gradient(1200px 680px at 15% -8%, rgba(59,130,246,0.10), transparent 60%),
          radial-gradient(1000px 620px at 110% 0%, rgba(96,165,250,0.08), transparent 55%),
          @BG0@ !important;
    }
    /* Scrollbars finas, arredondadas, com a cor da marca (o padrão do Chromium é feio). */
    ::-webkit-scrollbar { width: 11px; height: 11px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, @BRAND@, @BRAND2@);
        border-radius: 999px; border: 2px solid rgba(0,0,0,0.25);
    }
    ::-webkit-scrollbar-thumb:hover { background: @BRAND2@; }
    /* Seleção de texto com a cor da marca. */
    ::selection { background: rgba(59,130,246,0.35); color: #fff; }
    /* Foco de teclado mais elegante (acessibilidade sem perder beleza). */
    :focus-visible { outline: 2px solid @BRAND2@ !important; outline-offset: 2px !important; }
    """)


def _html_splash() -> str:
    """HTML da tela de abertura (splash) mostrada ENQUANTO o motor e o app sobem — para que
    nunca exista um instante de 'tela morta'. Marca + tagline + barra de progresso animada,
    tudo autocontido (sem rede)."""
    return _aplicar_tokens("""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<style>
  :root { color-scheme: dark; }
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { height:100%; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, Roboto, sans-serif;
    color: @TEXTO@; overflow:hidden;
    background:
      radial-gradient(900px 540px at 20% -10%, rgba(59,130,246,0.22), transparent 60%),
      radial-gradient(760px 520px at 108% 8%, rgba(96,165,250,0.16), transparent 55%),
      @BG0@;
    display:flex; align-items:center; justify-content:center;
  }
  .wrap { text-align:center; transform: translateY(-4%); }
  .logo {
    font-weight:800; letter-spacing:-0.02em; line-height:1;
    font-size: 64px;
    background: linear-gradient(120deg, #fff 10%, @BRAND2@ 60%, @BRAND@ 100%);
    -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
    filter: drop-shadow(0 6px 30px rgba(59,130,246,0.35));
  }
  .mark { display:inline-flex; align-items:center; gap:18px; }
  .orb {
    width:54px; height:54px; border-radius:16px;
    background: conic-gradient(from 210deg, @BRAND@, @BRAND2@, #22d3ee, @BRAND@);
    box-shadow: 0 10px 40px rgba(59,130,246,0.45), inset 0 0 18px rgba(255,255,255,0.25);
    animation: spin 5.5s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .tag { margin-top:18px; color:@TEXTO2@; font-size:16px; letter-spacing:0.02em; font-weight:500; }
  .bar { margin:34px auto 0; width:320px; height:6px; border-radius:999px;
         background: rgba(255,255,255,0.08); overflow:hidden; }
  .bar > i { display:block; height:100%; width:40%; border-radius:999px;
             background: linear-gradient(90deg, transparent, @BRAND@, @BRAND2@, transparent);
             animation: slide 1.25s ease-in-out infinite; }
  @keyframes slide { 0%{transform:translateX(-120%)} 100%{transform:translateX(320%)} }
  .status { margin-top:16px; color:@TEXTO2@; font-size:13px; min-height:18px; }
  .foot { position:fixed; bottom:22px; left:0; right:0; text-align:center;
          color:rgba(154,164,178,0.55); font-size:12px; letter-spacing:0.04em; }
  @media (prefers-reduced-motion: reduce) { .orb,.bar>i { animation:none; } }
</style></head>
<body>
  <div class="wrap">
    <div class="mark"><div class="orb"></div><div class="logo">OpenRotas</div></div>
    <div class="tag">Motor Nacional de Inteligência Logística</div>
    <div class="bar"><i></i></div>
    <div class="status" id="s">Preparando o ambiente…</div>
  </div>
  <div class="foot">Edição Desktop · todo o Brasil, offline-first</div>
  <script>
    var msgs = ["Preparando o ambiente…","Carregando as bases nacionais…",
                "Ligando o motor de rotas…","Montando a interface…","Quase lá…"];
    var i=0, el=document.getElementById('s');
    setInterval(function(){ i=(i+1)%msgs.length; el.textContent=msgs[i]; }, 1700);
  </script>
</body></html>""")


def abrir(url: str, icone: str | None = None, perfil_dir: str | None = None) -> bool:
    """Abre a janela nativa (Chromium embarcado) apontando para `url` (o Streamlit local).
    Mostra o splash até a página carregar e injeta o tema premium. Bloqueia até a janela
    fechar. Devolve True se a janela nativa rodou; False se o QtWebEngine não está disponível
    ou falhou ao iniciar (o chamador então tenta outra via). Nunca levanta.

    `perfil_dir`: pasta para o PERFIL PERSISTENTE do Chromium (cookies + localStorage em disco),
    para a SESSÃO DE LOGIN sobreviver ao fechar/reabrir (sem isto, o perfil é efêmero e o login
    'não cola')."""
    try:
        from PySide6.QtCore import Qt, QUrl, QTimer
        from PySide6.QtGui import QIcon, QDesktopServices
        from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import (QWebEngineScript, QWebEngineSettings,
                                             QWebEngineProfile, QWebEnginePage)
    except Exception as e:
        logger.info("QtWebEngine indisponível (%s).", e)
        return False

    # Página que abre links target=_blank / window.open no NAVEGADOR DO SISTEMA (o "Continuar
    # para o Google →" e demais links externos deixam de ser "mortos" na janela embarcada).
    class _Pagina(QWebEnginePage):
        def createWindow(self, _tipo):
            _temp = QWebEnginePage(self.profile(), self)
            def _abrir_externo(_u):
                try:
                    QDesktopServices.openUrl(_u)
                finally:
                    _temp.deleteLater()
            _temp.urlChanged.connect(_abrir_externo)
            return _temp

    try:
        # Compatibilidade de GPU/drivers variados no Windows: contexto GL compartilhado é
        # exigido pelo QtWebEngine; flags do Chromium habilitam fallback de software e evitam
        # exigências de sandbox que travariam em alguns ambientes.
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                              "--no-sandbox --disable-gpu-sandbox --enable-features=OverlayScrollbar")
        try:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        except Exception:
            pass

        app = QApplication.instance() or QApplication([])
        try:
            app.setApplicationName("OpenRotas")
            app.setOrganizationName("OpenRotas")
        except Exception:
            pass

        janela = QMainWindow()
        janela.setWindowTitle(TITULO)
        if icone and os.path.exists(icone):
            try:
                janela.setWindowIcon(QIcon(icone))
            except Exception:
                pass

        pilha = QStackedWidget()
        splash = QWebEngineView()
        splash.setHtml(_html_splash())

        # PERFIL PERSISTENTE (cookies + localStorage em disco) — é o que faz a SESSÃO de login
        # "colar" e sobreviver ao fechar/reabrir. Sem perfil nomeado, o Chromium é efêmero.
        view = QWebEngineView()
        try:
            if perfil_dir:
                os.makedirs(perfil_dir, exist_ok=True)
            _profile = QWebEngineProfile("openrotas", app)   # perfil NOMEADO = persistente
            if perfil_dir:
                _profile.setPersistentStoragePath(perfil_dir)
                _profile.setCachePath(perfil_dir)
            _profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
            _pagina = _Pagina(_profile, view)
            view.setPage(_pagina)
        except Exception:
            logger.warning("Não foi possível criar perfil persistente; seguindo com o padrão.",
                           exc_info=True)

        # Tema premium: injeta o CSS depois que o documento carrega (persiste nos reruns do
        # Streamlit, que apenas repintam o DOM sem recarregar a página).
        try:
            js = (
                "(function(){var id='openrotas-desktop-theme';"
                "if(document.getElementById(id))return;"
                "var s=document.createElement('style');s.id=id;"
                "s.textContent=%s;document.head.appendChild(s);})();"
            ) % _js_string(_css_premium())
            script = QWebEngineScript()
            script.setName("openrotas-premium")
            script.setSourceCode(js)
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setRunsOnSubFrames(False)
            view.page().scripts().insert(script)
        except Exception:
            logger.debug("Falha ao registrar o script de tema premium.", exc_info=True)

        # Reforço: reinjeta a cada carga concluída (SPA) e troca o splash pela app.
        def _ao_carregar(ok):
            try:
                if ok:
                    view.page().runJavaScript(js)
                    pilha.setCurrentWidget(view)
            except Exception:
                pass
        try:
            view.loadFinished.connect(_ao_carregar)
        except Exception:
            pass

        # Ajustes de conforto/segurança do motor.
        try:
            st = view.settings()
            st.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
            st.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
            st.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            # Permite window.open/target=_blank (roteados para o navegador do sistema via
            # _Pagina.createWindow) — necessário para o "Continuar para o Google →" não ser morto.
            st.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        except Exception:
            pass

        pilha.addWidget(splash)
        pilha.addWidget(view)
        pilha.setCurrentWidget(splash)
        janela.setCentralWidget(pilha)

        # Tamanho/estado inicial: janela grande, começa maximizada (cara de software completo).
        janela.resize(1440, 920)
        janela.setMinimumSize(1024, 700)
        janela.showMaximized()

        # Dispara o carregamento da app. Timeout de segurança: se não carregar, mostra a app
        # assim mesmo (melhor que ficar no splash para sempre).
        view.load(QUrl(url))

        def _timeout():
            try:
                if pilha.currentWidget() is splash:
                    pilha.setCurrentWidget(view)
            except Exception:
                pass
        QTimer.singleShot(90000, _timeout)

        logger.info("Janela nativa (QtWebEngine) aberta em %s", url)
        app.exec()
        return True
    except Exception:
        logger.exception("Falha ao abrir a janela nativa (QtWebEngine).")
        return False


def _js_string(s: str) -> str:
    """Serializa uma string Python para um literal JavaScript seguro (via JSON)."""
    import json
    return json.dumps(s)
