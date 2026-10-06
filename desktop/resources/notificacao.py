# -*- coding: utf-8 -*-
"""OpenRotas Desktop — NOTIFICAÇÃO NATIVA do Windows (toast).

Usada para avisar o usuário quando um estudo termina, mesmo com a janela minimizada/em 2º plano.
Totalmente DEFENSIVO e NÃO-REGRESSIVO: fora do Windows (ou se nada funcionar) vira no-op e nunca
levanta. Ordem de tentativa: (1) winotify (pura-Python, robusto, empacotado no desktop);
(2) PowerShell + WinRT (sem instalar nada); (3) no-op."""
from __future__ import annotations

import os
import logging
import subprocess

logger = logging.getLogger("openrotas.desktop.notificacao")


def _windows() -> bool:
    return os.name == "nt"


def _via_winotify(titulo: str, mensagem: str) -> bool:
    try:
        from winotify import Notification
        Notification(app_id="OpenRotas", title=titulo, msg=mensagem).show()
        return True
    except Exception:
        return False


def _via_powershell(titulo: str, mensagem: str) -> bool:
    """Toast via WinRT direto no PowerShell — não precisa instalar nada no Windows 10/11."""
    try:
        def _esc(s):
            return str(s).replace("'", "''")
        ps = (
            "$ErrorActionPreference='Stop';"
            "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
            "$tpl=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            "$tx=$tpl.GetElementsByTagName('text');"
            "$tx.Item(0).AppendChild($tpl.CreateTextNode('%s'))>$null;"
            "$tx.Item(1).AppendChild($tpl.CreateTextNode('%s'))>$null;"
            "$toast=[Windows.UI.Notifications.ToastNotification]::new($tpl);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('OpenRotas').Show($toast);"
            % (_esc(titulo), _esc(mensagem))
        )
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       creationflags=creation, timeout=12,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def notificar(titulo: str, mensagem: str) -> bool:
    """Mostra uma notificação nativa do Windows. Devolve True se conseguiu; False (no-op) fora
    do Windows ou se todas as vias falharem. NUNCA levanta."""
    try:
        if not _windows():
            return False
        if _via_winotify(titulo, mensagem):
            return True
        return _via_powershell(titulo, mensagem)
    except Exception:
        logger.debug("Falha ao notificar (ignorada).", exc_info=True)
        return False


def disponivel() -> bool:
    """True se há alguma via de notificação plausível (apenas no Windows)."""
    return _windows()
