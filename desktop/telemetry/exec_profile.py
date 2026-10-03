# -*- coding: utf-8 -*-
"""OpenRotas Desktop — PERFIL DE EXECUÇÃO / TELEMETRIA LOCAL (§42).

Registro 100% LOCAL (fica no perfil do usuário, nunca sai do computador — §31/§42) do que o
software fez: cada execução de interesse (uma rota calculada, um lote processado, um motor usado,
uma falha) vira uma linha JSONL. Serve para:

  • o usuário ver no Diagnóstico "o que o app andou fazendo e quão rápido" (§17/§42);
  • a lógica adaptativa de desempenho aprender com o histórico (quais motores respondem, tempos
    médios) sem depender de nuvem;
  • depurar problemas pós-fato ("ontem ficou lento") com dados reais, não achismo.

Projeto defensivo e barato: append em arquivo texto, rotação por tamanho, tudo em stdlib, e NUNCA
levanta para o chamador (telemetria jamais pode derrubar o app). Sem rede, sem PII além do que o
chamador explicitamente registrar."""
from __future__ import annotations

import os
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("openrotas.desktop.telemetry")

_LOCK = threading.Lock()                 # append concorrente seguro dentro do processo
_ROTACAO_BYTES = 5 * 1024 * 1024         # 5 MB por arquivo antes de rotacionar
_MANTER_LINHAS = 2000                    # ao rotacionar, preserva as N linhas mais recentes


def _arquivo_padrao() -> Path:
    """Caminho do JSONL no perfil do usuário. Resolve via desktop_config; degrada para ./logs."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        import desktop_config as cfg
        base = cfg.user_data_dir() / "logs"
    except Exception:
        base = Path.cwd() / "logs"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base / "exec_profile.jsonl"


def _resolver(caminho) -> Path:
    return Path(caminho) if caminho else _arquivo_padrao()


def _rotacionar_se_preciso(p: Path):
    """Se o arquivo passou do limite, mantém só as últimas _MANTER_LINHAS (janela deslizante)."""
    try:
        if not p.exists() or p.stat().st_size < _ROTACAO_BYTES:
            return
        with open(p, "r", encoding="utf-8") as f:
            linhas = f.readlines()
        if len(linhas) <= _MANTER_LINHAS:
            return
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(linhas[-_MANTER_LINHAS:])
    except Exception:
        logger.debug("[TELEMETRIA] rotação falhou (ignorado).", exc_info=True)


def registrar(evento: dict, caminho=None) -> bool:
    """Acrescenta UM evento (dict JSON-serializável) ao JSONL local, carimbando ts (epoch) e
    iso (UTC) se ausentes. Devolve True se gravou. NUNCA levanta."""
    p = _resolver(caminho)
    try:
        reg = dict(evento or {})
        reg.setdefault("ts", time.time())
        reg.setdefault("iso", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        linha = json.dumps(reg, ensure_ascii=False, default=str)
        with _LOCK:
            with open(p, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
            _rotacionar_se_preciso(p)
        return True
    except Exception:
        logger.debug("[TELEMETRIA] registro falhou (ignorado).", exc_info=True)
        return False


class cronometro:
    """Context manager que cronometra um bloco e registra a duração ao sair (§42).

        with cronometro("rota", motor="osrm_local"):
            ...   # calcula a rota

    Registra {tipo, evento:'rota', ms, ok, erro?, **extra}. Exceções no bloco são registradas
    (ok=False) e RE-LEVANTADAS (telemetria observa, não engole o erro do chamador)."""

    def __init__(self, evento: str, caminho=None, **extra):
        self.evento = evento
        self.caminho = caminho
        self.extra = extra
        self._t0 = None

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        ms = round((time.perf_counter() - self._t0) * 1000.0, 1)
        reg = {"tipo": "duracao", "evento": self.evento, "ms": ms, "ok": exc_type is None}
        if exc_type is not None:
            reg["erro"] = "%s: %s" % (getattr(exc_type, "__name__", exc_type), exc)
        reg.update(self.extra)
        registrar(reg, self.caminho)
        return False      # não suprime a exceção


def listar(n: int = 50, caminho=None) -> list:
    """Últimos `n` eventos (mais recentes por último), já desserializados. [] em falha."""
    p = _resolver(caminho)
    try:
        if not p.exists():
            return []
        with open(p, "r", encoding="utf-8") as f:
            linhas = f.readlines()
        eventos = []
        for ln in linhas[-max(1, n):]:
            ln = ln.strip()
            if not ln:
                continue
            try:
                eventos.append(json.loads(ln))
            except Exception:
                continue
        return eventos
    except Exception:
        logger.debug("[TELEMETRIA] leitura falhou (ignorado).", exc_info=True)
        return []


def resumo(caminho=None) -> dict:
    """Agrega o histórico local para o Diagnóstico (§17/§42): total de eventos, por evento, e
    tempos (média/p95/máx em ms) por 'evento' de duração, além de contagem de ok/erro. Barato:
    uma passada pelo arquivo. {} se não houver nada."""
    p = _resolver(caminho)
    try:
        if not p.exists():
            return {"total": 0, "por_evento": {}, "tempos": {}, "ok": 0, "erro": 0}
        total = ok = erro = 0
        por_evento: dict = {}
        tempos: dict = {}          # evento -> lista de ms
        with open(p, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    e = json.loads(ln)
                except Exception:
                    continue
                total += 1
                ev = str(e.get("evento", e.get("tipo", "?")))
                por_evento[ev] = por_evento.get(ev, 0) + 1
                if "ok" in e:
                    if e.get("ok"):
                        ok += 1
                    else:
                        erro += 1
                if isinstance(e.get("ms"), (int, float)):
                    tempos.setdefault(ev, []).append(float(e["ms"]))
        agregados = {}
        for ev, ms in tempos.items():
            ms_ord = sorted(ms)
            n = len(ms_ord)
            p95 = ms_ord[min(n - 1, int(round(0.95 * (n - 1))))]
            agregados[ev] = {
                "n": n,
                "media_ms": round(sum(ms_ord) / n, 1),
                "p95_ms": round(p95, 1),
                "max_ms": round(ms_ord[-1], 1),
            }
        return {"total": total, "por_evento": por_evento, "tempos": agregados, "ok": ok, "erro": erro}
    except Exception:
        logger.debug("[TELEMETRIA] resumo falhou (ignorado).", exc_info=True)
        return {"total": 0, "por_evento": {}, "tempos": {}, "ok": 0, "erro": 0}


def limpar(caminho=None) -> bool:
    """Apaga o histórico local (o usuário manda nos próprios dados — §31/§42). True se removeu."""
    p = _resolver(caminho)
    try:
        if p.exists():
            p.unlink()
        return True
    except Exception:
        return False


def _cli(argv=None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "resumo"
    if cmd == "resumo":
        r = resumo()
        print("Perfil de execução local (telemetria):")
        print("  eventos: %s  (ok=%s, erro=%s)" % (r["total"], r["ok"], r["erro"]))
        for ev, c in sorted(r["por_evento"].items(), key=lambda kv: -kv[1]):
            t = r["tempos"].get(ev)
            if t:
                print("   • %-16s %4d×   média %sms | p95 %sms | máx %sms"
                      % (ev, c, t["media_ms"], t["p95_ms"], t["max_ms"]))
            else:
                print("   • %-16s %4d×" % (ev, c))
        return 0
    if cmd == "listar":
        n = int(argv[1]) if len(argv) > 1 else 20
        for e in listar(n):
            print(json.dumps(e, ensure_ascii=False))
        return 0
    if cmd == "limpar":
        print("histórico apagado" if limpar() else "nada a apagar / falha")
        return 0
    print("uso: exec_profile.py [resumo|listar [N]|limpar]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
