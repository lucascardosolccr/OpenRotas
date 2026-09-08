# -*- coding: utf-8 -*-
"""[CLOUD-DADOS - 447ª geração] Bootstrap de dados pesados para o deploy no Streamlit Cloud.

O repositório versiona apenas os dados que cabem no GitHub (grafos ~45MB, CSVs SNIRH
leves, 10 das 12 camadas derivadas do IBGE). Os arquivos grandes demais para o limite
de 100MB/arquivo do GitHub (drenagem.parquet + rodovias.parquet) e o catálogo completo
de estações ANA/SNIRH (snirh_estacaos.csv) são publicados como ASSETS de um GitHub
Release deste repositório e baixados sob demanda pelo app quando ausentes.

Módulo PURAMENTE Python (sem Streamlit) para poder ser testado fora do Streamlit.
Fail-open: qualquer falha de rede/armazenamento apenas informa, nunca quebra a seção.
"""

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REPO = "lucascardosolccr/OpenRotas"
RELEASE_TAG = "dados-geoespaciais-v1"
RELEASE_BASE = "https://github.com/%s/releases/download/%s/" % (REPO, RELEASE_TAG)

# Cada item: nome lógico -> {asset: nome no release, destino: caminho relativo à raiz do
# projeto, bytes: tamanho esperado (para validar download incompleto), rotulo: exibição}.
EXTRAS = {
    "drenagem": {
        "asset": "drenagem.parquet",
        "destino": os.path.join("data", "brasil", "ibge", "derivadas", "drenagem.parquet"),
        "bytes": 451400139,
        "rotulo": "Drenagem (hidrografia detalhada IBGE BC250)",
    },
    "rodovias": {
        "asset": "rodovias.parquet",
        "destino": os.path.join("data", "brasil", "ibge", "derivadas", "rodovias.parquet"),
        "bytes": 121744788,
        "rotulo": "Rede rodoviária oficial IBGE",
    },
    "estacoes": {
        "asset": "snirh_estacaos.csv",
        "destino": "snirh_estacaos.csv",
        "bytes": 91130543,
        "rotulo": "Catálogo completo de estações ANA/SNIRH",
    },
}


def raiz_projeto():
    """Raiz do repositório (onde ficam os CSVs SNIRH e data/)."""
    return _RAIZ


def caminho_absoluto(nome):
    """Caminho absoluto onde o arquivo deve ficar, dado o nome lógico do item."""
    info = EXTRAS.get(nome)
    if not info:
        return None
    return os.path.join(_RAIZ, info["destino"])


def ausente(nome, tolerancia_pct=0.10):
    """True se o arquivo do item não existe ou está muito menor do que o esperado."""
    info = EXTRAS.get(nome)
    if not info:
        return False
    _p = os.path.join(_RAIZ, info["destino"])
    if not os.path.exists(_p):
        return True
    try:
        _tamanho = os.path.getsize(_p)
    except Exception:
        return True
    return _tamanho < info["bytes"] * (1.0 - tolerancia_pct)


def ausentes(somente_geoespacial=False, somente_para=None):
    """Lista de itens (nomes lógicos) que ainda faltam no disco."""
    _nomes = ["drenagem", "rodovias"] if somente_geoespacial else sorted(EXTRAS.keys())
    if somente_para is not None:
        _nomes = [n for n in _nomes if n in set(somente_para)]
    return [n for n in _nomes if ausente(n)]


def _baixar_um(nome, progresso=None):
    """Baixa um item da Release e valida o tamanho. Retorna (ok, mensagem)."""
    import urllib.request

    info = EXTRAS.get(nome)
    if not info:
        return False, "Item desconhecido: %s" % nome
    _dest = os.path.join(_RAIZ, info["destino"])
    try:
        os.makedirs(os.path.dirname(_dest) or _RAIZ, exist_ok=True)
    except Exception:
        pass
    _url = RELEASE_BASE + info["asset"]
    _tmp = _dest + ".part"
    _baixados = [0]
    try:
        def _repor(_blocos, _tam_bloco, _total):
            _baixados[0] += _tam_bloco
            if progresso is not None:
                try:
                    progresso(_blocos * _tam_bloco, _total or info["bytes"])
                except Exception:
                    pass

        with urllib.request.urlopen(_url, timeout=120) as _resp, open(_tmp, "wb") as _fh:
            _total = None
            try:
                _total = int(_resp.headers.get("Content-Length") or 0) or None
            except Exception:
                _total = None
            _acum = 0
            while True:
                _chunk = _resp.read(1024 * 256)
                if not _chunk:
                    break
                _fh.write(_chunk)
                _acum += len(_chunk)
                _baixados[0] = _acum
                if progresso is not None:
                    try:
                        progresso(_acum, _total or info["bytes"])
                    except Exception:
                        pass
        if os.path.getsize(_tmp) < info["bytes"] * 0.9:
            try:
                os.remove(_tmp)
            except Exception:
                pass
            return False, "Download incompleto de %s (tamanho esperado: %d bytes)." % (nome, info["bytes"])
        os.replace(_tmp, _dest)
        return True, "%s baixado com sucesso (%.1f MB)." % (nome.title(), os.path.getsize(_dest) / 1048576)
    except Exception as _e:
        try:
            if os.path.exists(_tmp):
                os.remove(_tmp)
        except Exception:
            pass
        return False, "Falha ao baixar %s: %s" % (nome, _e)


def baixar_ausentes(somente_geoespacial=False, progresso=None, somente_para=None):
    """Baixa todos os itens ausentes. Retorna (sucesso_total, relatorio[{nome, ok, msg}]).
    Fail-open: nunca levanta."""
    _relatorio = []
    _sucesso = True
    try:
        for _nome in ausentes(somente_geoespacial=somente_geoespacial, somente_para=somente_para):
            _ok, _msg = _baixar_um(_nome, progresso=progresso)
            _relatorio.append({"nome": _nome, "ok": _ok, "msg": _msg})
            _sucesso = _sucesso and _ok
    except Exception as _e:
        return False, [{"nome": "?", "ok": False, "msg": "Falha geral no bootstrap: %s" % _e}]
    return _sucesso, _relatorio


def resumo_faltantes():
    """Texto curto descrevendo o que falta + tamanho total (para exibir nos botões)."""
    _faltas = ausentes()
    if not _faltas:
        return ""
    _mb = sum(EXTRAS[n]["bytes"] for n in _faltas) / 1048576
    _rotulos = [EXTRAS[n]["rotulo"] for n in _faltas] + ["Total: %.0f MB" % _mb]
    return "Faltam: " + "; ".join(_rotulos)


if __name__ == "__main__":
    _faltas = ausentes()
    if not _faltas:
        print("Todos os dados pesados já presentes.")
    else:
        print("Faltantes:")
        for _n in _faltas:
            _i = EXTRAS[_n]
            print("  - %s -> %s (%.1f MB)" % (_i["rotulo"], os.path.join(_RAIZ, _i["destino"]), _i["bytes"] / 1048576))
        print(resumo_faltantes())