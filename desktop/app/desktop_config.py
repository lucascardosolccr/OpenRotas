# -*- coding: utf-8 -*-
"""OpenRotas Desktop — camada de CONFIGURAÇÃO (isolada da aplicação web).

Este módulo NÃO altera a aplicação web. Ele apenas PREPARA o ambiente local para que o
MESMO `streamlit_app.py` rode como um software de desktop, ativando as vantagens que só
existem na máquina do usuário — sem tocar numa linha do app web. A estratégia é usar os
pontos de extensão que a app JÁ lê (st.secrets / variáveis de ambiente), de modo que:

  • OSRM_URL  → aponta para um motor de rotas LOCAL (opcional), e a melhoria já no código
                (fast-fail do scraper quando há motor confiável) acelera o lote sozinha;
  • cache     → vai para um diretório PERSISTENTE no perfil do usuário (sobrevive a tudo);
  • workers   → a app já dimensiona pelos núcleos da CPU (num PC bom, usa mais naturalmente);
  • segredos  → Supabase (URL+anon) injetados via secrets.toml local, para o login funcionar.

Decisão de arquitetura (ver desktop/README.md): a edição desktop REUTILIZA a aplicação web
inteira (zero perda de funcionalidade) e a embrulha numa janela nativa — em vez de reescrever
a UI, o que arriscaria perder recursos. As vantagens locais entram por configuração.

Puro e defensivo: nunca levanta de propósito; em erro, degrada para padrões seguros.
"""
from __future__ import annotations

import os
import sys
import json
import logging
from pathlib import Path

logger = logging.getLogger("openrotas.desktop.config")

APP_NAME = "OpenRotas"
# Versão da edição desktop — FONTE ÚNICA DA VERDADE (§19). O instalador (openrotas.iss) e o
# verificador de atualizações (app_update.py) leem/casam com este valor.
APP_VERSION = "0.1.0"
# Porta local do servidor Streamlit embutido (alta, improvável de colidir).
PORTA_LOCAL = int(os.environ.get("OPENROTAS_PORT", "8537"))


# ---------------------------------------------------------------------------
# Localização de arquivos — funciona tanto em DEV (rodando do repositório) quanto
# EMPACOTADO (PyInstaller onedir, onde os recursos ficam ao lado do executável).
# ---------------------------------------------------------------------------
def app_root() -> Path:
    """Raiz onde vive o streamlit_app.py e as bases. Em DEV = raiz do repositório
    (dois níveis acima de desktop/app/). Empacotado = pasta do bundle (sys._MEIPASS
    para onefile, ou o diretório do executável para onedir)."""
    # PyInstaller define sys.frozen e, no onefile, sys._MEIPASS.
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        return Path(base)
    # DEV: .../OpenRotas/desktop/app/desktop_config.py → raiz do repo
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    """Diretório PERSISTENTE de dados do usuário (cache/logs/config), fora da pasta de
    instalação — assim uma atualização do app NÃO apaga cache nem configurações (§19).
    Windows: %LOCALAPPDATA%\\OpenRotas ; demais: ~/.local/share/OpenRotas."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    d = Path(base) / APP_NAME
    return d


def ensure_user_dirs() -> dict:
    """Cria (idempotente) a árvore persistente do usuário e devolve os caminhos."""
    base = user_data_dir()
    paths = {
        "base": base,
        "cache": base / "cache",
        "logs": base / "logs",
        "config": base / "config",
        "exports": base / "exports",
        "data_local": base / "data_local",   # grafos/mapas grandes instalados à parte (§19/§32)
    }
    for p in paths.values():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.warning("Não foi possível criar %s", p, exc_info=True)
    return paths


# ---------------------------------------------------------------------------
# Hardware — dimensionamento automático (§24/§25). Sem exigir psutil (fallback nativo).
# ---------------------------------------------------------------------------
def detectar_hardware() -> dict:
    cpus = os.cpu_count() or 4
    ram_gb = _ram_total_gb()
    # Perfil automático: PC robusto → performance; modesto → equilibrado.
    if ram_gb and ram_gb >= 16 and cpus >= 8:
        perfil = "performance"
    elif ram_gb and ram_gb >= 8:
        perfil = "equilibrado"
    else:
        perfil = "economico"
    return {"cpus": cpus, "ram_gb": ram_gb, "perfil": perfil}


def _ram_total_gb():
    # 1) psutil se disponível (mais preciso/portável)
    try:
        import psutil  # type: ignore
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    # 2) Windows nativo
    if os.name == "nt":
        try:
            import ctypes
            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MS(); ms.dwLength = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return round(ms.ullTotalPhys / (1024 ** 3), 1)
        except Exception:
            return None
    # 3) POSIX
    try:
        return round((os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3), 1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Config local do usuário (desktop.json) — OSRM_URL, Supabase, modo offline…
# ---------------------------------------------------------------------------
def carregar_config_usuario() -> dict:
    """Lê <user_data>/config/desktop.json (criado no 1º uso a partir do exemplo).
    Nunca levanta — devolve {} se não existir/estiver inválido."""
    cfg_path = user_data_dir() / "config" / "desktop.json"
    try:
        if cfg_path.exists():
            return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("desktop.json inválido — usando padrões.", exc_info=True)
    return {}


def preparar_secrets_e_env(paths: dict) -> dict:
    """Escreve um .streamlit/secrets.toml LOCAL (ao lado do app) a partir da config do
    usuário, e devolve o dicionário de variáveis de ambiente para o processo do Streamlit.

    NÃO toca no app web: apenas popula st.secrets (SUPABASE_*, OSRM_URL…) que a app já lê.
    Segredos ficam no perfil do usuário, nunca commitados (§42)."""
    cfg = carregar_config_usuario()
    # 1) secrets.toml ao lado do streamlit_app.py (onde o Streamlit procura).
    linhas = []
    for chave in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "OSRM_URL", "VALHALLA_URL",
                  "GRAPHHOPPER_URL", "ORS_API_KEY", "GRAPHHOPPER_API_KEY", "GOOGLE_MAPS_API_KEY", "APP_URL"):
        val = cfg.get(chave) or os.environ.get(chave)
        if val:
            linhas.append('%s = "%s"' % (chave, str(val).replace('"', '\\"')))
    try:
        st_dir = app_root() / ".streamlit"
        st_dir.mkdir(parents=True, exist_ok=True)
        secrets_path = st_dir / "secrets.toml"
        # Só sobrescreve se temos algo a escrever OU se não existe ainda (não apaga um
        # secrets.toml que o usuário tenha editado à mão com nada).
        if linhas:
            secrets_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    except Exception:
        logger.warning("Não foi possível preparar secrets.toml local.", exc_info=True)

    # 2) Variáveis de ambiente do processo Streamlit (headless, local, sem telemetria).
    env = dict(os.environ)
    env.update({
        "STREAMLIT_SERVER_PORT": str(PORTA_LOCAL),
        "STREAMLIT_SERVER_ADDRESS": "127.0.0.1",
        "STREAMLIT_SERVER_HEADLESS": "true",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        "STREAMLIT_GLOBAL_DEVELOPMENT_MODE": "false",
        # Cache persistente do app (diskcache) apontado para o perfil do usuário.
        "OPENROTAS_CACHE_DIR": str(paths["cache"]),
        "OPENROTAS_DESKTOP": "1",  # sinalizador para futuros ajustes opt-in (ver README/roadmap)
    })
    return env


def perfil_desempenho(hw: dict | None = None) -> dict:
    """[Etapa 5 / §24/§25] Recomenda parâmetros de desempenho a partir do hardware, SEM impor
    complexidade ao usuário (modo automático). Nota honesta: a aplicação já dimensiona os workers
    de rota pelos núcleos da CPU (min(32, max(8, CPU*4))) e usa disco local persistente — então,
    rodando localmente, o paralelismo já escala sozinho. Este perfil é informativo (mostrado no
    diagnóstico) e base para ajustes opt-in futuros, sem tocar na app web (§1)."""
    hw = hw or detectar_hardware()
    cpus = hw.get("cpus") or 4
    ram = hw.get("ram_gb") or 8
    workers = min(32, max(8, cpus * 4))                  # espelha a fórmula já usada pela app
    cache_mb = int(min(4096, max(512, (ram or 8) * 128)))  # ~1/8 da RAM, entre 512 MB e 4 GB
    return {
        "modo": hw.get("perfil", "equilibrado"),
        "workers_rota": workers,
        "cache_mb_sugerido": cache_mb,
        "observacao": "a app já escala workers pela CPU automaticamente ao rodar local",
    }


def resumo_config() -> dict:
    """Snapshot legível para log/diagnóstico de inicialização."""
    hw = detectar_hardware()
    cfg = carregar_config_usuario()
    return {
        "app_root": str(app_root()),
        "user_data": str(user_data_dir()),
        "porta": PORTA_LOCAL,
        "hardware": hw,
        "osrm_local": bool(cfg.get("OSRM_URL")),
        "offline": bool(cfg.get("offline")),
    }
