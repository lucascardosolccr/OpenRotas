# -*- coding: utf-8 -*-
"""OpenRotas Desktop — ORQUESTRAÇÃO DE PROVISIONAMENTO DE DADOS (§12/§18/§19/§32).

Camada PURA e testável que fica ENTRE a interface (CLI `--provisionar-grafo`, GUI "Central de
Dados") e os mecanismos de baixo nível (osrm_manager, resource_manager, local_data). Reúne, num
só lugar, as operações que o usuário final dispara para ter TODO O BRASIL completo na máquina:

  • inventario()        — o que está instalado / falta (bases + grafo), tamanho, prontidão offline;
  • baixar_grafo()      — baixa o grafo OSRM do Brasil (vários GB) para a PASTA DE DADOS que o app
                          lê, com callback de progresso; usa o graph_url configurado OU o padrão
                          turnkey (desktop_config.url_grafo_padrao) — o usuário não precisa achar URL;
  • reparar_bases()     — repara/atualiza as bases embarcadas sem reinstalar (resource_manager);
  • ativar_roteamento_local() — grava osrm.mode='docker' no desktop.json (roteamento offline,
                          requer Docker) — opt-in explícito;
  • abrir_pasta_dados() — abre a pasta de dados do usuário no explorador de arquivos do SO.

Tudo defensivo: nunca levanta para o chamador; cada função devolve um dict/estado textual. A GUI
é só um invólucro fino disto — assim a LÓGICA é coberta por testes sem precisar de display."""
from __future__ import annotations

import os
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent / "app", _AQUI.parent, _AQUI.parent / "data_local", _AQUI.parent / "engines"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.provisionamento")


def _cfg():
    import desktop_config as cfg
    return cfg


def _grafo_valido(caminho) -> bool:
    """True se `caminho` aponta para um grafo OSRM utilizável. O OSRM 5.x (MLD) NÃO cria um
    arquivo-base literal '<base>.osrm' — o grafo É a família '<base>.osrm.*'. Portanto o
    caminho-base devolvido por garantir_grafo/instalar_grafo pode não existir como arquivo:
    aceitamos o arquivo-base avulso OU a presença da família '<base>.osrm.*'. (Sem isto, um
    download/extração BEM-SUCEDIDO era reportado como falha "sem detalhe".)"""
    if not caminho:
        return False
    try:
        if os.path.exists(caminho):
            return True
        b = Path(caminho)
        return any(b.parent.glob(b.name + ".*"))
    except Exception:
        return False


def pasta_de_dados() -> Path:
    """A PASTA que o app lê para dados grandes instalados à parte (grafo OSRM). É para cá que o
    download vai — 'direto para a pasta do software', como pedido. Fica no perfil do usuário, fora
    da instalação (sobrevive a updates)."""
    try:
        return _cfg().ensure_user_dirs()["data_local"]
    except Exception:
        return _cfg().user_data_dir() / "data_local"


# Arquivos essenciais de um grafo MLD SERVÍVEL (o osrm-routed --algorithm mld os exige). Uma
# extração PARCIAL/interrompida não terá todos — e aí o grafo não serve. Checar o conjunto
# evita (a) travar o botão 'Baixar o mapa' sobre uma extração incompleta e (b) ligar o
# roteamento sobre um grafo quebrado.
_MLD_SUF_ESSENCIAIS = (".mldgr", ".partition", ".cells", ".cell_metrics")


def _registry():
    """Devolve (módulo local_data, LocalDataRegistry) apontando para o app_root + o data_local do
    perfil do usuário. Levanta se local_data/config indisponível — os chamadores tratam. (Antes
    esta função era REFERENCIADA mas não existia: bases_ausentes caía sempre no except e retornava
    [], nunca reportando base faltando — bug corrigido ao defini-la.)"""
    cfg = _cfg()
    import local_data
    reg = local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")
    return local_data, reg


# Espaço de disco necessário para BAIXAR + EXTRAIR o grafo com folga: partes (~6,7 GB) + tar
# concatenado + família extraída coexistem por um instante. 16 GB é uma folga conservadora.
_ESPACO_GRAFO_NECESSARIO = 16 * 1024 ** 3


def espaco_livre_bytes(pasta=None) -> int:
    """Bytes livres no volume da `pasta` (padrão: pasta de dados). 0 se não der para medir."""
    try:
        alvo = Path(pasta) if pasta else pasta_de_dados()
        alvo.mkdir(parents=True, exist_ok=True)
        return int(shutil.disk_usage(str(alvo)).free)
    except Exception:
        return 0


def checar_espaco_para_grafo(pasta=None) -> dict:
    """Verifica ANTES do download se há espaço para baixar+extrair o grafo. Evita gastar ~6,7 GB
    de download para só então falhar na extração por falta de disco. {ok, livre, necessario,
    detalhe}. Defensivo: se não medir o disco (livre=0), NÃO bloqueia (ok=True) para não dar falso
    negativo — melhor tentar do que barrar por engano."""
    livre = espaco_livre_bytes(pasta)
    nec = _ESPACO_GRAFO_NECESSARIO
    if livre <= 0:
        return {"ok": True, "livre": 0, "necessario": nec,
                "detalhe": "não foi possível medir o espaço livre; seguindo mesmo assim."}
    ok = livre >= nec
    if ok:
        detalhe = "espaço suficiente (%s livres)." % humano_bytes(livre)
    else:
        detalhe = ("espaço insuficiente para baixar/extrair o mapa: %s livres, ~%s necessários. "
                   "Libere espaço e tente de novo." % (humano_bytes(livre), humano_bytes(nec)))
    return {"ok": ok, "livre": livre, "necessario": nec, "detalhe": detalhe}


def verificar_integridade(conf: dict | None = None) -> dict:
    """Verifica a INTEGRIDADE das bases instaladas (não só se existem: se ABREM no formato certo,
    via local_data.legivel — rodapé do parquet / 1 KB do gzip / 1ª linha do csv). Detecta corrupção
    que a checagem de existência não pega. Devolve {ok, corrompidas, faltantes_essenciais,
    checadas, detalhe}. Nunca levanta."""
    out = {"ok": True, "corrompidas": [], "faltantes_essenciais": [], "checadas": 0, "detalhe": ""}
    try:
        local_data, reg = _registry()
    except Exception as e:
        out["ok"] = False
        out["detalhe"] = "verificação indisponível: %s" % e
        return out
    try:
        for d in local_data.CATALOGO:
            if getattr(d, "formato", "") == "osrm":
                continue                                   # o grafo é tratado à parte
            existe = reg.existe(d.chave)
            if not existe:
                if getattr(d, "essencial", False):
                    out["faltantes_essenciais"].append(d.chave)
                continue
            out["checadas"] += 1
            try:
                if not reg.legivel(d.chave):
                    out["corrompidas"].append(d.chave)
            except Exception:
                out["corrompidas"].append(d.chave)
        out["ok"] = not out["corrompidas"] and not out["faltantes_essenciais"]
        if out["ok"]:
            out["detalhe"] = "todas as %s bases verificadas estão íntegras ✓" % out["checadas"]
        else:
            partes = []
            if out["corrompidas"]:
                partes.append("%d corrompida(s): %s" % (len(out["corrompidas"]),
                                                        ", ".join(out["corrompidas"])))
            if out["faltantes_essenciais"]:
                partes.append("%d essencial(is) faltando: %s"
                              % (len(out["faltantes_essenciais"]),
                                 ", ".join(out["faltantes_essenciais"])))
            out["detalhe"] = "; ".join(partes) + ". Use 'Reparar/instalar bases nacionais'."
    except Exception as e:
        out["ok"] = False
        out["detalhe"] = "falha na verificação: %s" % e
    return out


def grafo_instalado() -> bool:
    """True SÓ se há um grafo OSRM MLD COMPLETO na pasta de dados do usuário.

    O OSRM 5.x (MLD) não gera um arquivo-base literal '<base>.osrm' — o grafo É a família
    '<base>.osrm.*' (.cells/.mldgr/.partition/.cell_metrics/...). Exigimos os arquivos ESSENCIAIS
    do MLD presentes para um mesmo prefixo '<base>.osrm' (um grafo íntegro sempre os tem; uma
    extração parcial não). Compat: um arquivo-base '*.osrm' avulso (formatos antigos) também conta."""
    try:
        d = pasta_de_dados()
        if not d.exists():
            return False
        nomes = {p.name for p in d.glob("*.osrm.*")}
        bases = {n[:n.index(".osrm") + len(".osrm")] for n in nomes if ".osrm" in n}
        for b in bases:
            if all((b + suf) in nomes for suf in _MLD_SUF_ESSENCIAIS):
                return True
        return next(d.glob("*.osrm"), None) is not None   # compat: arquivo-base avulso
    except Exception:
        return False


def roteamento_local_ativo(conf: dict | None = None) -> bool:
    """True se o desktop.json já está com o roteamento local ligado (osrm.mode em
    local/auto/docker). Usado para LIGAR sozinho quando o mapa está presente mas o modo ficou
    'off' (ex.: o grafo foi extraído num clique que, por um bug antigo, reportou falha)."""
    try:
        oc = _osrm_cfg_efetivo(conf)
        return str(oc.get("mode", "")).strip().lower() in ("local", "auto", "docker")
    except Exception:
        return False


def status_motor_rotas(conf: dict | None = None) -> dict:
    """Status AO VIVO do motor de rotas — não só o que está CONFIGURADO, mas se o motor local
    está REALMENTE respondendo. Pinga o OSRM local (127.0.0.1) com uma rota curtíssima e diz se
    as rotas estão indo pelo motor LOCAL (rápido/offline) ou caindo no OSRM PÚBLICO (lento). Torna
    visível a falha silenciosa que já custou caro ('diz ativo, mas lento'). Nunca levanta.

    Devolve: {grafo_instalado, motor_nativo_disponivel, modo, url_local, local_no_ar,
              usando_publico, detalhe}."""
    out = {"grafo_instalado": False, "motor_nativo_disponivel": False, "modo": "off",
           "url_local": "", "local_no_ar": False, "usando_publico": True, "detalhe": ""}
    try:
        try:
            import osrm_manager
        except ImportError:
            from engines import osrm_manager
    except Exception as e:
        out["detalhe"] = "motor indisponível: %s" % e
        return out
    try:
        oc = _osrm_cfg_efetivo(conf)
        modo = (str(oc.get("mode", "") or "").strip().lower() or "off")
        try:
            porta = int(oc.get("port", 5000) or 5000)
        except Exception:
            porta = 5000
        url = str(oc.get("url") or ("http://127.0.0.1:%d" % porta))
        out["modo"] = modo
        out["url_local"] = url
        out["grafo_instalado"] = grafo_instalado()
        try:
            out["motor_nativo_disponivel"] = bool(osrm_manager.motor_nativo_disponivel())
        except Exception:
            out["motor_nativo_disponivel"] = False
        no_ar = False
        try:
            no_ar = bool(osrm_manager.health(url, timeout=3.0))
        except Exception:
            no_ar = False
        out["local_no_ar"] = no_ar
        out["usando_publico"] = not no_ar
        if no_ar:
            out["detalhe"] = "motor local NO AR em %s — rotas rápidas e offline ✓" % url
        elif modo in ("local", "auto", "docker"):
            if out["grafo_instalado"]:
                out["detalhe"] = ("roteamento local ligado, mas o motor ainda não está respondendo "
                                  "(ele sobe ao ABRIR o app; a 1ª rota 'aquece' o mapa). Até lá, as "
                                  "rotas usam o OSRM público (online).")
            else:
                out["detalhe"] = ("roteamento local ligado, mas o mapa do Brasil não está instalado — "
                                  "as rotas usam o OSRM público. Baixe o mapa para rotear offline.")
        else:
            out["detalhe"] = "roteamento local desligado — rotas usam o OSRM público (online)."
    except Exception as e:
        out["detalhe"] = "falha ao consultar o motor de rotas: %s" % e
    return out


def checar_atualizacao() -> dict:
    """Verifica se há uma versão NOVA do app publicada (app_update.verificar). Devolve
    {atual, remota, ha_atualizacao, url_instalador, disponivel, detalhe}. Nunca levanta —
    offline/sem release → disponivel=False."""
    try:
        import app_update
    except Exception:
        try:
            sys.path.insert(0, str(_AQUI.parent / "app"))
            import app_update
        except Exception as e:
            return {"atual": "", "remota": None, "ha_atualizacao": False, "url_instalador": None,
                    "disponivel": False, "detalhe": "verificação indisponível: %s" % e}
    try:
        return app_update.verificar()
    except Exception as e:
        return {"atual": "", "remota": None, "ha_atualizacao": False, "url_instalador": None,
                "disponivel": False, "detalhe": "erro: %s" % e}


def resumo_desempenho() -> dict:
    """Resumo do DESEMPENHO local das rotas a partir da telemetria (exec_profile). Devolve o dict
    de resumo + uma linha humana 'texto' pronta para a UI. Nunca levanta; {} se não houver dados."""
    base = {"total": 0, "ok": 0, "erro": 0, "tempos": {}, "texto": "Sem dados de desempenho ainda."}
    try:
        import exec_profile
    except Exception:
        try:
            sys.path.insert(0, str(_AQUI.parent / "telemetry"))
            import exec_profile
        except Exception:
            return base
    try:
        r = exec_profile.resumo() or {}
    except Exception:
        return base
    r.setdefault("total", 0)
    r.setdefault("ok", 0)
    r.setdefault("erro", 0)
    r.setdefault("tempos", {})
    if not r.get("total"):
        r["texto"] = "Sem dados de desempenho ainda (faça algumas rotas)."
        return r
    # escolhe o evento de rota mais frequente para a linha-resumo
    tempos = r.get("tempos") or {}
    alvo = None
    for ev in ("rota", "route", "roteamento"):
        if ev in tempos:
            alvo = (ev, tempos[ev])
            break
    if alvo is None and tempos:
        alvo = sorted(tempos.items(), key=lambda kv: -(kv[1] or {}).get("n", 0))[0]
    if alvo:
        ev, t = alvo
        r["texto"] = ("Desempenho (%s): %s× · média %sms · p95 %sms (ok=%s, erro=%s)"
                      % (ev, (t or {}).get("n", "?"), (t or {}).get("media_ms", "?"),
                         (t or {}).get("p95_ms", "?"), r.get("ok", 0), r.get("erro", 0)))
    else:
        r["texto"] = "Eventos: %s (ok=%s, erro=%s)" % (r["total"], r["ok"], r["erro"])
    return r


def relatorio_diagnostico() -> str:
    """Relatório de autodiagnóstico COMPLETO (diagnostics.relatorio_texto) para mostrar na UI.
    Nunca levanta — devolve uma mensagem de erro legível em caso de falha."""
    try:
        import diagnostics
    except Exception:
        try:
            sys.path.insert(0, str(_AQUI.parent / "app"))
            import diagnostics
        except Exception as e:
            return "Diagnóstico indisponível: %s" % e
    try:
        return diagnostics.relatorio_texto()
    except Exception as e:
        return "Falha ao gerar o diagnóstico: %s: %s" % (type(e).__name__, e)


def _osrm_cfg_efetivo(conf: dict | None = None) -> dict:
    """Bloco osrm do desktop.json COM o graph_url resolvido (configurado > padrão turnkey)."""
    cfg = _cfg()
    try:
        conf = conf if conf is not None else cfg.carregar_config_usuario()
    except Exception:
        conf = {}
    oc = dict((conf or {}).get("osrm") or {})
    oc["graph_url"] = cfg.resolver_graph_url(conf)
    return oc


def docker_disponivel() -> bool:
    """True se o Docker está instalado e rodando (necessário só para SERVIR o roteamento local)."""
    try:
        try:
            import osrm_manager
        except ImportError:
            from engines import osrm_manager   # app congelado: resolve pelo pacote
        return osrm_manager._docker_disponivel()
    except Exception:
        return False


def tamanho_estimado_grafo_bytes() -> int:
    """Estimativa (fixa, honesta) do tamanho do grafo do Brasil, para a UI avisar o usuário antes
    do download. ~6,7 GB (soma das partes publicadas na Release). 0 se desconhecido."""
    return 6_700_000_000


def inventario(conf: dict | None = None) -> dict:
    """Retrato COMPLETO para a Central de Dados: lista de recursos (bases + grafo) com estado e
    tamanho, prontidão offline e um resumo de contagem. Reutiliza resource_manager/local_data;
    nunca levanta — devolve estrutura vazia/parcial em falha."""
    out = {"recursos": [], "offline": {}, "grafo_instalado": grafo_instalado(),
           "pasta_dados": str(pasta_de_dados()), "resumo": {}}
    try:
        import resource_manager as rm
        out["recursos"] = rm.status(_osrm_cfg_efetivo(conf))
    except Exception:
        logger.warning("[PROV] status dos recursos indisponível.", exc_info=True)
    try:
        import desktop_config as cfg
        import local_data
        reg = local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")
        out["offline"] = reg.offline_pronto()
    except Exception:
        logger.warning("[PROV] prontidão offline indisponível.", exc_info=True)
    try:
        recs = out["recursos"]
        out["resumo"] = {
            "total": len(recs),
            "instalados": sum(1 for r in recs if r.get("instalado")),
            "faltam_obrigatorios": [r["chave"] for r in recs
                                    if r.get("obrigatorio") and not r.get("instalado")],
            "faltam_opcionais": [r["chave"] for r in recs
                                 if not r.get("obrigatorio") and not r.get("instalado")],
        }
    except Exception:
        pass
    return out


def baixar_grafo(progresso=None, conf: dict | None = None) -> dict:
    """Baixa/garante o grafo OSRM do Brasil (download único de vários GB) DIRETO para a pasta de
    dados que o app usa, com callback de `progresso` (dict por atualização) para a barra da UI.
    Usa o graph_url configurado OU o padrão turnkey. Devolve {ok, caminho, detalhe}. Não levanta.

    Observação honesta: ter o grafo habilita o roteamento LOCAL/offline, mas SERVIR exige Docker
    (ver ativar_roteamento_local). Sem Docker, o grafo fica pronto e o app segue no OSRM público."""
    try:
        try:
            import osrm_manager
        except ImportError:
            from engines import osrm_manager   # app congelado: resolve pelo pacote
    except Exception as e:
        return {"ok": False, "caminho": None, "detalhe": "osrm_manager indisponível: %s" % e}
    oc = _osrm_cfg_efetivo(conf)
    if not str(oc.get("graph_url", "")).strip():
        return {"ok": False, "caminho": None, "detalhe": "sem graph_url (nem padrão) — nada a baixar"}
    # GUARDA DE DISCO: barra ANTES de gastar ~6,7 GB de download se não houver espaço para extrair.
    # Só bloqueia quando o disco foi medido E está claramente insuficiente (evita falso negativo).
    _disco = checar_espaco_para_grafo()
    if not _disco["ok"]:
        _escrever_diag(_disco["detalhe"])
        return {"ok": False, "caminho": None,
                "detalhe": "não foi possível baixar o mapa: %s" % _disco["detalhe"]}
    # Captura o MOTIVO REAL (fase 'erro') aqui, independentemente da UI — assim ele SEMPRE entra na
    # mensagem final E num arquivo de diagnóstico, mesmo que o evento não chegue à tela a tempo.
    _capt = {"erro": ""}

    def _wrap(ev):
        try:
            if (ev or {}).get("fase") == "erro" and (ev or {}).get("detalhe"):
                _capt["erro"] = ev["detalhe"]
        except Exception:
            pass
        if progresso is not None:
            try:
                progresso(ev)
            except Exception:
                pass

    try:
        caminho = osrm_manager.garantir_grafo(oc, pasta_de_dados(), progresso=_wrap)
    except Exception as e:
        logger.warning("[PROV] download do grafo falhou.", exc_info=True)
        _escrever_diag("erro: %s" % e)
        return {"ok": False, "caminho": None, "detalhe": "erro: %s" % e}
    if _grafo_valido(caminho):
        return {"ok": True, "caminho": caminho, "detalhe": "grafo pronto em %s" % caminho}
    causa = _capt["erro"] or "sem detalhe (ver log openrotas-desktop.log)"
    _escrever_diag(causa)
    msg = ("não foi possível baixar/preparar o mapa. [causa: %s]. "
           "Dica: se o navegador baixa as partes mas o app não, use 'Importar mapa baixado "
           "pelo navegador' abaixo." % causa)
    return {"ok": False, "caminho": None, "detalhe": msg}


def _escrever_diag(causa: str) -> None:
    """Grava a causa da última falha de download num arquivo fácil de achar, para suporte."""
    try:
        destino = pasta_de_dados()
        destino.mkdir(parents=True, exist_ok=True)
        import time as _t
        (destino / "ultimo_erro_download.txt").write_text(
            "OpenRotas — última falha ao baixar/preparar o mapa\n%s\n\ncausa: %s\n"
            % (_t.strftime("%Y-%m-%d %H:%M:%S"), causa), encoding="utf-8")
    except Exception:
        pass


def importar_grafo_de_pasta(pasta, progresso=None) -> dict:
    """Instala o mapa a partir de arquivos JÁ BAIXADOS (pelo navegador) numa pasta — SEM rede.
    Caminho garantido quando o download dentro do app falha. Devolve {ok, caminho, detalhe}."""
    try:
        try:
            import osrm_manager
        except ImportError:
            from engines import osrm_manager
    except Exception as e:
        return {"ok": False, "caminho": None, "detalhe": "osrm_manager indisponível: %s" % e}
    try:
        caminho = osrm_manager.instalar_grafo_de_partes_locais(pasta, pasta_de_dados(), progresso=progresso)
    except Exception as e:
        logger.warning("[PROV] import local do grafo falhou.", exc_info=True)
        return {"ok": False, "caminho": None, "detalhe": "erro: %s" % e}
    if _grafo_valido(caminho):
        return {"ok": True, "caminho": caminho, "detalhe": "mapa instalado de %s" % pasta}
    return {"ok": False, "caminho": None,
            "detalhe": "não foi possível montar o mapa a partir da pasta (confira se baixou todas as partes)."}


def _reassemblar_bigparts() -> dict:
    """Reassembla as bases NACIONAIS grandes (drenagem/rodovias) a partir dos pedaços _bigparts/
    embarcados, via montar_bases_grandes.py (idempotente, sha256). Para completar as bases
    nacionais mesmo sem rede. {ok, detalhe}. Nunca levanta."""
    cfg = _cfg()
    try:
        import importlib.util
        for base in (cfg.app_root(), cfg.app_root() / "desktop", Path(__file__).resolve().parents[2]):
            script = Path(base) / "montar_bases_grandes.py"
            if script.exists():
                spec = importlib.util.spec_from_file_location("_montar_bg_prov", script)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                rc = mod.montar(verbose=False)
                return {"ok": rc == 0, "detalhe": "bases grandes reassembladas" if rc == 0 else "reassembly com pendências"}
        return {"ok": False, "detalhe": "montar_bases_grandes.py não encontrado"}
    except Exception as e:
        logger.warning("[PROV] reassembly de _bigparts falhou.", exc_info=True)
        return {"ok": False, "detalhe": "erro: %s" % e}


def bases_ausentes(conf: dict | None = None) -> list:
    """Lista as chaves das bases NACIONAIS ausentes (exclui o grafo OSRM, tratado à parte). []
    quando tudo presente. Nunca levanta."""
    try:
        import local_data
        _, reg = _registry()
        return [d.chave for d in local_data.CATALOGO
                if d.formato != "osrm" and not reg.existe(d.chave)]
    except Exception:
        return []


def reparar_bases(progresso=None, conf: dict | None = None) -> dict:
    """Repara/atualiza as bases (sem reinstalar) via resource_manager.reparar_tudo, usando o
    dados_base_url da config (se houver) e provisionando o grafo se faltar. Devolve o relatório
    do resource_manager (ou {ok:False,...} em falha). `progresso` é aceito por simetria (o reparo
    de bases é rápido; emite início/fim)."""
    cfg = _cfg()
    try:
        conf = conf if conf is not None else cfg.carregar_config_usuario()
    except Exception:
        conf = {}
    if progresso:
        try:
            progresso({"fase": "reparando"})
        except Exception:
            pass
    # 1º: completa as bases NACIONAIS a partir dos pedaços embarcados (_bigparts/), sem depender
    # de rede — resolve drenagem/rodovias ausentes em qualquer máquina. 2º: reparo/atualização
    # normal (resource_manager) para o resto, usando dados_base_url se houver.
    reassembly = _reassemblar_bigparts()
    try:
        import resource_manager as rm
        rel = rm.reparar_tudo(osrm_cfg=_osrm_cfg_efetivo(conf),
                              base_url=str((conf or {}).get("dados_base_url", "") or ""))
        rel["reassembly_bigparts"] = reassembly
        if progresso:
            try:
                progresso({"fase": "concluido", "ok": bool(rel.get("ok"))})
            except Exception:
                pass
        return rel
    except Exception as e:
        logger.warning("[PROV] reparo de bases falhou.", exc_info=True)
        return {"ok": False, "detalhe": "erro: %s" % e}


def motor_nativo_disponivel() -> bool:
    """True se o app traz o motor NATIVO embarcado (osrm-routed) — serve o grafo local SEM Docker."""
    try:
        try:
            import osrm_manager
        except ImportError:
            from engines import osrm_manager   # app congelado: resolve pelo pacote
        return osrm_manager.motor_nativo_disponivel()
    except Exception:
        return False


def ativar_roteamento_local(conf: dict | None = None) -> dict:
    """Liga o roteamento LOCAL/offline gravando osrm.mode='auto' no desktop.json do usuário — o
    modo mais inteligente e turnkey: usa o motor NATIVO embarcado (sem Docker) quando disponível e,
    só se não houver, tenta o Docker; senão cai no OSRM público. Sem servidor 24h, sem PC ligado:
    o motor roda apenas enquanto o app está aberto. Devolve {ok, nativo, docker, detalhe}. Preserva
    o resto da config; nunca levanta."""
    cfg = _cfg()
    try:
        destino = cfg.user_data_dir() / "config" / "desktop.json"
        atual = {}
        if destino.exists():
            try:
                atual = json.loads(destino.read_text(encoding="utf-8"))
            except Exception:
                atual = {}
        oc = dict(atual.get("osrm") or {})
        oc["mode"] = "auto"
        # Garante um graph_url utilizável (padrão turnkey se vazio) para achar/baixar o grafo.
        if not str(oc.get("graph_url", "") or "").strip():
            oc["graph_url"] = cfg.url_grafo_padrao()
        atual["osrm"] = oc
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")
        tem_nativo = motor_nativo_disponivel()
        tem_docker = docker_disponivel()
        if tem_nativo:
            detalhe = "roteamento local ligado (motor nativo embarcado — sem Docker, rápido e offline)."
        elif tem_docker:
            detalhe = "roteamento local ligado (via Docker)."
        else:
            detalhe = ("roteamento local ligado (osrm.mode='auto'). Este build não traz o motor nativo "
                       "e não há Docker: o app seguirá no OSRM público até um motor local existir.")
        return {"ok": True, "nativo": tem_nativo, "docker": tem_docker, "detalhe": detalhe}
    except Exception as e:
        logger.warning("[PROV] ativação do roteamento local falhou.", exc_info=True)
        return {"ok": False, "nativo": False, "docker": False, "detalhe": "erro: %s" % e}


def pasta_por_tipo(tipo: str) -> Path:
    """Resolve a pasta de um 'tipo' para os atalhos da UI: 'dados' (grafo), 'exports' (dossiês),
    'logs' (openrotas-desktop.log) e 'downloads' (downloads feitos pelo app). Nunca levanta."""
    cfg = _cfg()
    try:
        base = cfg.user_data_dir()
    except Exception:
        base = pasta_de_dados().parent
    t = str(tipo or "").strip().lower()
    if t == "exports":
        return base / "exports"
    if t == "logs":
        return base / "logs"
    if t == "downloads":
        return Path(os.path.join(os.path.expanduser("~"), "Downloads"))
    return pasta_de_dados()          # 'dados' (padrão)


def abrir_pasta_dados(caminho: Path | None = None) -> bool:
    """Abre a pasta de dados no explorador do SO (Windows Explorer / Finder / xdg-open), para o
    usuário VER e manejar os arquivos baixados. Best-effort — devolve True se disparou o comando.
    Em ambiente headless/CI (sem DISPLAY, ou OPENROTAS_NO_NET), vira no-op e devolve False."""
    alvo = Path(caminho) if caminho else pasta_de_dados()
    try:
        alvo.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # Não tenta abrir GUI em ambiente sem sessão gráfica (ex.: CI).
    if os.environ.get("OPENROTAS_NO_NET") or (os.name == "posix" and not os.environ.get("DISPLAY")
                                              and sys.platform != "darwin"):
        return False
    try:
        if os.name == "nt":
            os.startfile(str(alvo))                       # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(alvo)])
        else:
            subprocess.Popen(["xdg-open", str(alvo)])
        return True
    except Exception:
        logger.info("[PROV] não foi possível abrir a pasta de dados.", exc_info=True)
        return False


def humano_bytes(n) -> str:
    """Formata bytes em unidade legível (KB/MB/GB). '—' se inválido."""
    try:
        n = float(n)
    except Exception:
        return "—"
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return ("%.0f %s" % (n, unidade)) if unidade == "B" else ("%.1f %s" % (n, unidade))
        n /= 1024.0
    return "%.1f PB" % n


def humano_velocidade(bps) -> str:
    try:
        import downloader
        return downloader.humano_velocidade(bps)
    except Exception:
        return (humano_bytes(bps) + "/s") if bps else "—"


def humano_eta(seg) -> str:
    try:
        import downloader
        return downloader.humano_eta(seg)
    except Exception:
        return "—"
