# -*- coding: utf-8 -*-
"""OpenRotas Desktop — DOWNLOADER ROBUSTO (§18/§20). Retomada + velocidade + ETA + retry + sha256.

Baixa um arquivo grande de forma resiliente:
  • RETOMADA (HTTP Range): se uma conexão cair em 70%, continua de onde parou (grava em .part e só
    renomeia ao final) — não reinicia do zero quando o servidor suporta Range;
  • PROGRESSO rico: callback com {baixado, total, pct, velocidade_bps, eta_s};
  • RETRY com backoff exponencial em erros transitórios (2s, 4s, 8s…);
  • VERIFICAÇÃO sha256 ao final (descarta e refaz se não bater — §20).

Testável sem rede: o "abridor" HTTP é INJETÁVEL (`abrir`), então os testes simulam servidor,
Range, queda no meio e retomada. Puro stdlib. Nunca levanta para o chamador."""
from __future__ import annotations

import os
import ssl
import time
import hashlib
import logging
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger("openrotas.desktop.downloader")

_BLOCO = 1024 * 256

# UA de navegador: alguns CDNs/limites tratam melhor um UA conhecido do que um genérico.
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpenRotas-Desktop/1.0"


def contexto_ssl():
    """Contexto TLS com uma loja de certificados CONFIÁVEL. Num app empacotado (PyInstaller) o
    Python embarcado às vezes não acha os certificados do sistema e RECUSA todo HTTPS (o download
    do GitHub falha enquanto o navegador baixa normal). Usar o CA bundle do `certifi` resolve isso
    de forma portátil. Fallback: contexto padrão do SO (no Windows usa a loja do sistema). NUNCA
    desliga a verificação."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            return None


def humano_bytes(n) -> str:
    try:
        n = float(n)
    except Exception:
        return "—"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return ("%.0f %s" % (n, u)) if u == "B" else ("%.1f %s" % (n, u))
        n /= 1024.0
    return "%.1f PB" % n


def humano_velocidade(bps) -> str:
    try:
        return humano_bytes(bps) + "/s" if bps and bps > 0 else "—"
    except Exception:
        return "—"


def humano_eta(seg) -> str:
    try:
        seg = int(seg)
    except Exception:
        return "—"
    if seg < 0:
        return "—"
    if seg < 60:
        return "%ds" % seg
    if seg < 3600:
        return "%dmin %02ds" % (seg // 60, seg % 60)
    return "%dh %02dmin" % (seg // 3600, (seg % 3600) // 60)


def _abrir_http(url, inicio=0, timeout=120):
    """Abre `url` a partir do byte `inicio` (Range). Devolve (fileobj, total_desta_resposta,
    range_ok). total_desta_resposta = bytes QUE ESTA resposta trará (Content-Length)."""
    headers = {"User-Agent": _UA}
    if inicio > 0:
        headers["Range"] = "bytes=%d-" % inicio
    req = urllib.request.Request(url, headers=headers)
    _ctx = contexto_ssl()
    resp = (urllib.request.urlopen(req, timeout=timeout, context=_ctx) if _ctx
            else urllib.request.urlopen(req, timeout=timeout))
    code = getattr(resp, "status", None) or resp.getcode()
    range_ok = (code == 206)                  # 206 = Partial Content (servidor honrou o Range)
    try:
        total = int(resp.headers.get("Content-Length") or 0)
    except Exception:
        total = 0
    return resp, total, range_ok


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _emitir(progresso, **campos):
    if progresso is None:
        return
    try:
        progresso(dict(campos))
    except Exception:
        pass


def baixar(url, destino, progresso=None, sha256: str = "", tentativas: int = 4, timeout: int = 120,
           abrir=None, retomar: bool = True, backoff_base: float = 2.0, dormir=None) -> dict:
    """Baixa `url` para `destino` com retomada/velocidade/ETA/retry/sha256. Devolve
    {ok, caminho, bytes, sha256, tentativas, detalhe}. `abrir`/`dormir` injetáveis p/ teste."""
    abrir = abrir or _abrir_http
    dormir = dormir or time.sleep
    destino = Path(destino)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    part = destino.with_suffix(destino.suffix + ".part")

    ultimo_erro = ""
    for tentativa in range(1, max(1, tentativas) + 1):
        inicio = 0
        if retomar:
            try:
                inicio = part.stat().st_size if part.exists() else 0
            except Exception:
                inicio = 0
        try:
            fobj, total_resp, range_ok = abrir(url, inicio, timeout)
            # Se pedimos Range mas o servidor NÃO honrou (200 em vez de 206), recomeça do zero.
            if inicio > 0 and not range_ok:
                inicio = 0
            modo = "ab" if (inicio > 0 and range_ok) else "wb"
            total_abs = (total_resp + inicio) if range_ok else total_resp
            baixado = inicio
            t0 = time.time()
            try:
                with open(part, modo) as out:
                    while True:
                        bloco = fobj.read(_BLOCO)
                        if not bloco:
                            break
                        out.write(bloco)
                        baixado += len(bloco)
                        dt = max(1e-6, time.time() - t0)
                        vel = (baixado - inicio) / dt
                        eta = int((total_abs - baixado) / vel) if (total_abs and vel > 0) else -1
                        pct = round(100.0 * baixado / total_abs, 1) if total_abs else None
                        _emitir(progresso, fase="baixando", baixado=baixado, total=total_abs or None,
                                pct=pct, velocidade_bps=vel, eta_s=eta)
            finally:
                try:
                    fobj.close()
                except Exception:
                    pass
            # EOF PRECOCE sem erro: alguns servidores/proxies cortam o stream de um arquivo grande
            # SEM levantar exceção — read() devolve vazio antes do fim. Se o Content-Length era
            # conhecido e recebemos MENOS, NÃO é sucesso: renomear esse .part truncado para o
            # destino faria o grafo concatenar lixo (extração falha → "verifique conexão"). Trata
            # como falha transitória → a próxima tentativa RETOMA (Range) de onde parou.
            if total_abs and baixado < total_abs:
                raise IOError("transferência incompleta: %d de %d bytes (EOF precoce)"
                              % (baixado, total_abs))
            # integridade (§20)
            if sha256:
                got = _sha256(part)
                if got.lower() != str(sha256).lower():
                    try:
                        part.unlink()
                    except Exception:
                        pass
                    ultimo_erro = "sha256 não confere (esperado %s, obtido %s)" % (sha256[:12], got[:12])
                    # hash errado não é transitório: aborta sem retomar lixo.
                    return {"ok": False, "caminho": None, "bytes": 0, "sha256": got,
                            "tentativas": tentativa, "detalhe": ultimo_erro}
            tam = part.stat().st_size
            os.replace(str(part), str(destino))
            _emitir(progresso, fase="concluido", baixado=tam, total=tam, pct=100.0)
            return {"ok": True, "caminho": str(destino), "bytes": tam,
                    "sha256": sha256 or "", "tentativas": tentativa, "detalhe": "ok"}
        except Exception as e:
            # RECUPERAÇÃO DE .part COMPLETO: se o download já tinha terminado mas o processo morreu
            # ANTES do os.replace, o .part fica com o tamanho final; a retomada pede Range no/após o
            # EOF e o servidor responde HTTP 416 (Range Not Satisfiable). Isso NÃO é falha — o
            # arquivo está inteiro. Finaliza (conferindo sha, se houver) em vez de re-tentar à toa.
            if getattr(e, "code", None) == 416 and part.exists() and part.stat().st_size > 0:
                if sha256:
                    got = _sha256(part)
                    if got.lower() != str(sha256).lower():
                        try:
                            part.unlink()
                        except Exception:
                            pass
                        return {"ok": False, "caminho": None, "bytes": 0, "sha256": got,
                                "tentativas": tentativa,
                                "detalhe": "sha256 não confere (esperado %s, obtido %s)"
                                           % (sha256[:12], got[:12])}
                tam = part.stat().st_size
                os.replace(str(part), str(destino))
                _emitir(progresso, fase="concluido", baixado=tam, total=tam, pct=100.0)
                return {"ok": True, "caminho": str(destino), "bytes": tam,
                        "sha256": sha256 or "", "tentativas": tentativa,
                        "detalhe": "já estava completo (HTTP 416 na retomada)"}
            ultimo_erro = "%s" % e
            logger.info("[DL] tentativa %d/%d falhou (%s); manterá .part para retomar.",
                        tentativa, tentativas, e)
            if tentativa < tentativas:
                dormir(backoff_base ** tentativa)      # 2s, 4s, 8s…
            # mantém o .part para a próxima tentativa retomar
    return {"ok": False, "caminho": None, "bytes": 0, "sha256": "", "tentativas": tentativas,
            "detalhe": "falha após %d tentativa(s): %s" % (tentativas, ultimo_erro)}
