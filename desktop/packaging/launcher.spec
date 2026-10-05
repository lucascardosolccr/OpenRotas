# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — OpenRotas Desktop (build ONEDIR).

Por que ONEDIR (e não onefile): um software que carrega Streamlit + pandas/numpy/scikit +
bases grandes inicia MUITO mais rápido em onedir (o onefile descompacta tudo num temp a cada
abertura — lento e frágil para apps grandes). O instalador (Inno Setup) embrulha esta pasta
onedir num .exe de instalação. Prioriza desempenho/estabilidade/atualização, como pedido (§14).

Empacotar Streamlit exige coletar os metadados e arquivos estáticos dele e das libs de UI.
Este spec é o PONTO DE PARTIDA: builds são iterativos (§37) — rode na sua máquina Windows,
veja o que falta (hidden imports/datas) e acrescente. Começo com os coletores conhecidos.

Uso:
    cd desktop
    ..\\venv\\Scripts\\pyinstaller packaging\\launcher.spec --noconfirm
Saída: desktop\\build\\dist\\OpenRotas\\OpenRotas.exe (+ a pasta onedir)
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

REPO_ROOT = os.path.abspath(os.path.join(os.getcwd(), ".."))  # rode de dentro de desktop/

# --- Coleta COMPLETA das libs que carregam dados/estáticos por caminho (não só import) ---
_pacotes_coletar = [
    "streamlit", "altair", "pydeck", "plotly", "pandas", "numpy", "pyarrow",
    "sklearn", "scipy", "rapidfuzz", "geographiclib", "geopy", "diskcache",
    "cachetools", "unidecode", "supabase", "supabase_auth", "storage3", "postgrest",
    "realtime", "kaleido", "xlsxwriter", "openpyxl", "python_calamine",
    "streamlit_js_eval",
    # [JANELA NATIVA — PREFERIDA] PySide6/QtWebEngine: Chromium EMBARCADO no .exe. É o motor
    # da janela nativa (desktop/app/janela.py) e não depende de WebView2/navegador. collect_all
    # traz os plugins Qt, recursos do QtWebEngine (QtWebEngineProcess, ICU, locales) e binários.
    "PySide6", "shiboken6",
    # [JANELA NATIVA — FALLBACK] pywebview e dependências de runtime. SEM coletar 'webview', o
    # pacote congelado não encontra os backends de plataforma (webview.platforms.*) nem o
    # pythonnet/clr. Coletar tudo.
    "webview", "proxy_tools", "bottle", "typing_extensions",
    "clr_loader", "pythonnet",
]
datas, binaries, hiddenimports = [], [], []
for _pac in _pacotes_coletar:
    try:
        d, b, h = collect_all(_pac)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass
hiddenimports += collect_submodules("streamlit")
# Backends de plataforma do pywebview são importados DINAMICAMENTE (importlib), então a análise
# estática não os enxerga — congela-os explicitamente. No Windows o relevante é o edgechromium
# (WebView2) + winforms; os demais são inócuos se ausentes.
hiddenimports += collect_submodules("webview")
hiddenimports += [
    "webview.platforms.edgechromium", "webview.platforms.winforms",
    "webview.platforms.mshtml", "webview.platforms.cef",
    "clr", "clr_loader", "clr_loader.netfx", "clr_loader.ffi",
]

# [METADADOS - correção clássica Streamlit+PyInstaller] O Streamlit (e várias libs) leem a PRÓPRIA
# versão em runtime via importlib.metadata.version(...); sem os .dist-info embutidos, o app quebra
# ao iniciar com PackageNotFoundError. copy_metadata embute esses metadados no bundle. Defensivo.
for _meta in ("streamlit", "altair", "pandas", "numpy", "pyarrow", "plotly", "pydeck",
              "supabase", "supabase_auth", "scikit-learn", "scipy", "rapidfuzz",
              "streamlit-js-eval", "diskcache", "cachetools",
              "pywebview", "pythonnet", "clr_loader", "PySide6", "shiboken6"):
    try:
        datas += copy_metadata(_meta)
    except Exception:
        pass
# Módulos próprios do desktop (imports em nível de função / via __import__ que a análise
# estática pode não enxergar) — congela-os explicitamente no bundle.
hiddenimports += ["desktop_config", "diagnostics", "janela", "engines", "engines.osrm_manager"]
# QtWebEngine: módulos usados dinamicamente pela janela nativa.
hiddenimports += ["PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore",
                  "PySide6.QtWidgets", "PySide6.QtGui", "PySide6.QtCore", "PySide6.QtNetwork"]

# [IMPORTS DA APLICAÇÃO — correção do "No module named 'email.mime'"] O ponto de entrada da
# análise do PyInstaller é o launcher.py; o streamlit_app.py é COPIADO como dado e só roda em
# runtime, então os imports DELE (e dos módulos da app) NÃO eram vistos → módulos como
# email.mime.text, smtplib e deps de auth/inteligencia_geoespacial ficavam de fora do bundle.
# Correção abrangente (sem caça a guaxinim): (1) streamlit_app.py entra como script de análise
# (abaixo, no Analysis) para o PyInstaller seguir TODO o fecho de imports dele; (2) reforço aqui
# coletando submódulos da stdlib e dos pacotes próprios da app que possam ser importados de forma
# dinâmica/preguiçosa (a análise estática não enxerga esses).
for _pac_app in ("email", "auth", "inteligencia_geoespacial"):
    try:
        hiddenimports += collect_submodules(_pac_app)
    except Exception:
        pass
hiddenimports += [
    "semantica",
    "email.mime", "email.mime.text", "email.mime.multipart", "email.mime.base",
    "email.mime.application", "email.mime.nonmultipart", "email.mime.message",
    "email.mime.image", "email.mime.audio",
    "smtplib", "email.utils", "email.header", "email.encoders",
]

# [VARREDURA DE IMPORTS DA APP] Lê estaticamente (ast, SEM executar) todo o fecho de código da
# aplicação — streamlit_app.py, semantica.py e os pacotes auth/ e inteligencia_geoespacial/ — e
# acrescenta CADA módulo importado como hiddenimport. Assim qualquer dependência que só a app usa
# (e que a análise a partir do launcher.py não alcança) entra no bundle. Idempotente e tolerante a
# falhas; nomes inexistentes só geram aviso do PyInstaller, nunca erro.
import ast as _ast

def _varrer_imports(raiz):
    nomes = set()
    arquivos = []
    for _alvo in ("streamlit_app.py", "semantica.py"):
        _p = os.path.join(raiz, _alvo)
        if os.path.exists(_p):
            arquivos.append(_p)
    for _pkg in ("auth", "inteligencia_geoespacial"):
        _d = os.path.join(raiz, _pkg)
        if os.path.isdir(_d):
            for _r, _ds, _fs in os.walk(_d):
                if "test" in _r.replace("\\", "/"):   # ignora diretórios de teste
                    continue
                for _f in _fs:
                    if _f.endswith(".py"):
                        arquivos.append(os.path.join(_r, _f))
    for _arq in arquivos:
        try:
            _tree = _ast.parse(open(_arq, "r", encoding="utf-8").read(), filename=_arq)
        except Exception:
            continue
        for _node in _ast.walk(_tree):
            if isinstance(_node, _ast.Import):
                for _n in _node.names:
                    nomes.add(_n.name)
            elif isinstance(_node, _ast.ImportFrom):
                if _node.module and _node.level == 0:      # só imports absolutos
                    nomes.add(_node.module)
    return sorted(nomes)

try:
    hiddenimports += _varrer_imports(REPO_ROOT)
except Exception:
    pass
# Amostra de pares O/D do benchmark, servida ao lado do pacote engines.
_sample = os.path.join(REPO_ROOT, "desktop", "engines", "sample_pairs.csv")
if os.path.exists(_sample):
    datas.append((_sample, "engines"))
# Ícone do app (gerado por make_icon.py antes do empacotamento) — levado para a raiz do bundle
# para a JANELA NATIVA exibi-lo (janela.abrir procura em app_root()/openrotas.ico).
_ico = os.path.join(REPO_ROOT, "desktop", "installer", "openrotas.ico")
if os.path.exists(_ico):
    datas.append((_ico, "."))

# --- A APLICAÇÃO e as BASES embarcadas (reutiliza o app web por inteiro, §21/§34) ---
# Mapeadas para a MESMA estrutura relativa, pois o app as acessa por caminho relativo.
_itens = [
    "streamlit_app.py", "semantica.py", "auth", "inteligencia_geoespacial",
    ".streamlit", "data", "ne_rivers_10m",
    "hidrografia_nacional.pkl.gz", "amazonia_fluvial.pkl.gz", "snirh_rios.csv",
    "Localidades_Brasil_shp.zip", "ne_10m_rivers_lake_centerlines.zip",
]
for _it in _itens:
    _src = os.path.join(REPO_ROOT, _it)
    if os.path.exists(_src):
        # destino = raiz do bundle (mantém o mesmo nome relativo)
        datas.append((_src, _it if os.path.isdir(_src) else "."))

# [GRAFO EMBUTIDO - opcional] Se desktop/data_local/ tiver o grafo (brazil-latest.osrm*), ele é
# EMBUTIDO no bundle (instalador "gordo", com roteamento offline pronto). O workflow build-desktop
# coloca os arquivos lá quando embed_graph=true; sem eles, nada é embutido (instalador enxuto).
_data_local = os.path.join(REPO_ROOT, "desktop", "data_local")
if os.path.isdir(_data_local):
    for _fn in os.listdir(_data_local):
        if _fn.startswith("brazil-latest.osrm"):
            datas.append((os.path.join(_data_local, _fn), "data_local"))

block_cipher = None

a = Analysis(
    [os.path.join(REPO_ROOT, "desktop", "app", "launcher.py")],
    # pathex inclui desktop/ (pacote 'engines') e desktop/app (módulos soltos) além da raiz.
    pathex=[os.path.join(REPO_ROOT, "desktop"),
            os.path.join(REPO_ROOT, "desktop", "app"), REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # NÃO excluir tkinter: é usado para o DIÁLOGO DE ERRO NATIVO do launcher (mostra a causa
    # quando o motor não sobe, em vez de uma aba de navegador morta) e pela Central de Dados.
    excludes=["torch", "transformers", "tensorflow"],  # peso morto (não usados)
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="OpenRotas",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False,  # app de janela (sem console preto). Troque p/ True ao depurar o build.
    icon=os.path.join(REPO_ROOT, "desktop", "installer", "openrotas.ico")
        if os.path.exists(os.path.join(REPO_ROOT, "desktop", "installer", "openrotas.ico")) else None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name="OpenRotas",
)
