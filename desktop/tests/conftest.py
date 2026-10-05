# -*- coding: utf-8 -*-
"""Fixtures da suíte desktop.

Isola o PERFIL DE EXECUÇÃO (telemetria) de cada teste num diretório temporário: vários testes
exercitam os registradores que, por padrão, gravam no perfil do USUÁRIO
(<user_data>/logs/exec_profile.jsonl). Sem isso, a suíte poluiria o perfil real da máquina (e
acumularia eventos entre execuções). A redireção vale só durante os testes."""
import os
import sys

import pytest

_DESKTOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_DESKTOP, "telemetry"))


@pytest.fixture(autouse=True)
def _telemetria_isolada(tmp_path, monkeypatch):
    """Redireciona o JSONL padrão da telemetria para um tmp por teste (hermético)."""
    try:
        import exec_profile
        monkeypatch.setattr(exec_profile, "_arquivo_padrao",
                            lambda: tmp_path / "exec_profile.jsonl")
    except Exception:
        pass
    yield
