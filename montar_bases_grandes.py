#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reassembla as BASES NACIONAIS GRANDES a partir dos pedaços versionados.

drenagem.parquet (~451 MB — rede de drenagem/rios nacional) e rodovias.parquet (~121 MB — malha
rodoviária nacional) excedem o limite de 100 MB de um push comum do GitHub e o Git LFS está
bloqueado neste ambiente; por isso são versionadas em PEDAÇOS de <100 MB em
`data/brasil/ibge/derivadas/_bigparts/`. Este script concatena os pedaços de volta no .parquet
inteiro (com verificação sha256), para que o checkout fique com os dados nacionais COMPLETOS —
é rodado no build do instalador e no CI (e pode ser rodado à mão num clone de desenvolvimento).

Idempotente: se o .parquet já existe e o sha256 bate, não faz nada. Puro stdlib."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DERIVADAS = RAIZ / "data" / "brasil" / "ibge" / "derivadas"
PARTS = DERIVADAS / "_bigparts"
MANIFESTO = PARTS / "bases_grandes.json"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def montar(verbose: bool = True) -> int:
    if not MANIFESTO.exists():
        if verbose:
            print("Manifesto de bases grandes não encontrado (%s) — nada a montar." % MANIFESTO)
        return 0
    try:
        bases = json.loads(MANIFESTO.read_text(encoding="utf-8")).get("bases", [])
    except Exception as e:
        print("Manifesto inválido: %s" % e)
        return 1
    erros = 0
    for b in bases:
        nome, sha = b.get("nome"), str(b.get("sha256", "")).lower()
        if not nome:
            continue
        destino = DERIVADAS / nome
        # já montado e íntegro?
        if destino.exists() and (not sha or _sha256(destino).lower() == sha):
            if verbose:
                print("OK   %s já presente e íntegro." % nome)
            continue
        partes = sorted(PARTS.glob(nome + ".part*"))
        if not partes:
            print("FALTA %s: nenhum pedaço em %s" % (nome, PARTS))
            erros += 1
            continue
        if verbose:
            print("Montando %s a partir de %d pedaço(s)..." % (nome, len(partes)))
        tmp = destino.with_suffix(destino.suffix + ".tmp")
        try:
            with open(tmp, "wb") as out:
                for parte in partes:
                    with open(parte, "rb") as f:
                        while True:
                            bloco = f.read(1024 * 1024)
                            if not bloco:
                                break
                            out.write(bloco)
            if sha:
                got = _sha256(tmp).lower()
                if got != sha:
                    tmp.unlink()
                    print("ERRO  %s: sha256 não confere (esperado %s, obtido %s)" % (nome, sha[:12], got[:12]))
                    erros += 1
                    continue
            tmp.replace(destino)
            if verbose:
                print("OK   %s montado (%.0f MB)." % (nome, destino.stat().st_size / (1024 ** 2)))
        except Exception as e:
            print("ERRO ao montar %s: %s" % (nome, e))
            try:
                tmp.unlink()
            except Exception:
                pass
            erros += 1
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(montar(verbose="--silencioso" not in sys.argv))
