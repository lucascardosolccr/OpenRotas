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
    """Camada de tema PREMIUM injetada só no desktop. É ADITIVA: dá PROFUNDIDADE ESTÁTICA
    (sombras, cantos, brilho da marca, scrollbars) SEM reescrever as cores/o layout do design
    system da web.

    IMPORTANTE — SEM MOVIMENTO CONTÍNUO. Versões anteriores tinham um fundo "aurora" animado
    infinito e uma animação de ENTRADA do conteúdo (`ork-rise`) que o Streamlit REEXECUTA a cada
    rerun — no Chromium embarcado (QtWebEngine, muitas vezes render por software) isso fazia a
    tela "piscar o tempo inteiro". Também havia inclinação 3D seguindo o mouse. Tudo isso foi
    REMOVIDO: a camada agora é 100% estática (só transições curtas em hover/foco, que não
    repintam sozinhas). Sem flicker, mantendo o visual premium."""
    return _aplicar_tokens("""
    /* ===== OpenRotas Desktop — camada PREMIUM ESTÁTICA (injetada pela janela nativa) ===== */
    :root { --ork-ease: cubic-bezier(.2,.8,.2,1); }
    html, body, .stApp {
        -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
    }
    /* Cara de APP: esconde a barra/menu/rodapé do Streamlit. */
    #MainMenu, header[data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="stStatusWidget"], [data-testid="stDecoration"], footer {
        display: none !important; visibility: hidden !important;
    }
    .stApp > header { height: 0 !important; }
    .block-container { padding-top: 2.2rem !important; }

    /* ---- FUNDO com profundidade — ESTÁTICO (sem animação; não pisca) ---- */
    .stApp { background: @BG0@ !important; position: relative; }
    .stApp::before {
        content:""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
        background:
          radial-gradient(42vmax 42vmax at 12% -6%, rgba(59,130,246,0.16), transparent 60%),
          radial-gradient(38vmax 38vmax at 110% 6%, rgba(96,165,250,0.12), transparent 55%),
          radial-gradient(30vmax 30vmax at 50% 122%, rgba(34,211,238,0.10), transparent 60%);
        /* SEM animação e SEM filter:blur (blur de tela cheia animado = repaint constante/flicker) */
    }
    /* conteúdo acima do fundo */
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    [data-testid="stHeader"] { position: relative; z-index: 1; }

    /* ---- SUPERFÍCIES com PROFUNDIDADE estática; hover só muda SOMBRA/BORDA (sem transform) ---- */
    .mnil, [data-testid="stMetric"], [data-testid="stExpander"] details,
    [data-testid="stForm"], [data-testid="stAlert"], [data-testid="stNotification"],
    .stDataFrame, [data-testid="stTable"] {
        border-radius: 16px !important;
        box-shadow: 0 1px 0 rgba(255,255,255,.04) inset,
                    0 10px 28px rgba(0,0,0,.34), 0 2px 8px rgba(0,0,0,.22) !important;
        transition: box-shadow .2s var(--ork-ease), border-color .2s var(--ork-ease) !important;
    }
    .mnil:hover, [data-testid="stMetric"]:hover, [data-testid="stExpander"] details:hover,
    [data-testid="stForm"]:hover {
        box-shadow: 0 1px 0 rgba(255,255,255,.07) inset,
                    0 18px 40px rgba(0,0,0,.46), 0 6px 16px rgba(59,130,246,.18) !important;
        border-color: rgba(96,165,250,.40) !important;
    }
    /* Métricas (KPIs): valor com leve brilho da marca (estático) */
    [data-testid="stMetricValue"] {
        text-shadow: 0 0 22px rgba(96,165,250,.24);
        letter-spacing: -0.01em;
    }

    /* ---- BOTÕES: elevação sutil só em hover (sombra/brilho; sem shimmer, sem transform) ---- */
    .stButton > button, [data-testid^="stBaseButton"], [data-testid="baseButton-primary"] {
        transition: box-shadow .18s var(--ork-ease), filter .18s var(--ork-ease) !important;
    }
    .stButton > button:hover, [data-testid^="stBaseButton"]:hover {
        box-shadow: 0 8px 22px rgba(59,130,246,.30), 0 2px 8px rgba(0,0,0,.28) !important;
        filter: saturate(112%) brightness(1.03);
    }

    /* ---- INPUTS: foco luminoso da marca (só ao focar) ---- */
    [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div,
    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        transition: box-shadow .18s var(--ork-ease), border-color .18s var(--ork-ease) !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus,
    [data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {
        box-shadow: 0 0 0 3px rgba(59,130,246,.28), 0 6px 18px rgba(59,130,246,.18) !important;
        border-color: @BRAND2@ !important;
    }

    /* ---- TABS: aba ativa com brilho (estático) ---- */
    [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {
        box-shadow: 0 0 14px rgba(96,165,250,.6); border-radius: 999px;
    }

    /* ---- Scrollbars finas da marca ---- */
    ::-webkit-scrollbar { width: 11px; height: 11px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, @BRAND@, @BRAND2@);
        border-radius: 999px; border: 2px solid rgba(0,0,0,0.25);
    }
    ::-webkit-scrollbar-thumb:hover { background: @BRAND2@; }
    ::selection { background: rgba(59,130,246,0.35); color: #fff; }
    :focus-visible { outline: 2px solid @BRAND2@ !important; outline-offset: 2px !important; }

    /* ---- Acessibilidade: zera até as transições de hover/foco quando o usuário pede ---- */
    @media (prefers-reduced-motion: reduce) {
        .mnil, [data-testid="stMetric"], [data-testid="stExpander"] details,
        [data-testid="stForm"], .stButton > button, [data-testid^="stBaseButton"],
        .stTextInput input, .stNumberInput input, .stTextArea textarea {
            transition: none !important;
        }
    }
    """)


def _js_premium() -> str:
    """JS da camada premium. REMOVIDO o tilt 3D que seguia o mouse: ele reescrevia o `transform`
    dos cartões a cada movimento do mouse, forçando repaint contínuo (parte do "piscar") e era o
    efeito 3D que o usuário pediu para tirar. Mantém-se uma guarda idempotente (não faz nada) para
    não reinstalar nada nos reruns do Streamlit e para o contrato de injeção seguir igual. A
    profundidade agora é 100% CSS estático (ver _css_premium). Puro/defensivo."""
    return """
    try {
      if (!window.__orkPremium) {
        window.__orkPremium = true;
        /* Sem efeitos de movimento: a profundidade é estática (CSS). Nada a instalar aqui. */
      }
    } catch (e) {}
    """


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

        # Tema premium: injeta o CSS (uma vez) E instala o tilt 3D (idempotente) depois que o
        # documento carrega. Persiste nos reruns do Streamlit (o <head> não é recriado).
        try:
            js = (
                "(function(){try{var id='openrotas-desktop-theme';"
                "if(!document.getElementById(id)){var s=document.createElement('style');s.id=id;"
                "s.textContent=%s;document.head.appendChild(s);}}catch(e){}"
                "%s"
                "})();"
            ) % (_js_string(_css_premium()), _js_premium())
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
