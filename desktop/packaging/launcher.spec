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
]
datas, binaries, hiddenimports = [], [], []
for _pac in _pacotes_coletar:
    try:
        d, b, h = collect_all(_pac)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass
hiddenimports += collect_submodules("streamlit")

# [METADADOS - correção clássica Streamlit+PyInstaller] O Streamlit (e várias libs) leem a PRÓPRIA
# versão em runtime via importlib.metadata.version(...); sem os .dist-info embutidos, o app quebra
# ao iniciar com PackageNotFoundError. copy_metadata embute esses metadados no bundle. Defensivo.
for _meta in ("streamlit", "altair", "pandas", "numpy", "pyarrow", "plotly", "pydeck",
              "supabase", "supabase_auth", "scikit-learn", "scipy", "rapidfuzz",
              "streamlit-js-eval", "diskcache", "cachetools"):
    try:
        datas += copy_metadata(_meta)
    except Exception:
        pass
# Módulos próprios do desktop (imports em nível de função / via __import__ que a análise
# estática pode não enxergar) — congela-os explicitamente no bundle.
hiddenimports += ["desktop_config", "diagnostics", "engines", "engines.osrm_manager"]
# Amostra de pares O/D do benchmark, servida ao lado do pacote engines.
_sample = os.path.join(REPO_ROOT, "desktop", "engines", "sample_pairs.csv")
if os.path.exists(_sample):
    datas.append((_sample, "engines"))

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
    excludes=["tkinter", "torch", "transformers", "tensorflow"],  # peso morto (não usados)
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
