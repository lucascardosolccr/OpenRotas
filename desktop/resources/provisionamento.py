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


def pasta_de_dados() -> Path:
    """A PASTA que o app lê para dados grandes instalados à parte (grafo OSRM). É para cá que o
    download vai — 'direto para a pasta do software', como pedido. Fica no perfil do usuário, fora
    da instalação (sobrevive a updates)."""
    try:
        return _cfg().ensure_user_dirs()["data_local"]
    except Exception:
        return _cfg().user_data_dir() / "data_local"


def grafo_instalado() -> bool:
    """True se já existe um grafo .osrm provisionado na pasta de dados do usuário."""
    try:
        d = pasta_de_dados()
        return d.exists() and next(d.glob("*.osrm"), None) is not None
    except Exception:
        return False


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
    try:
        caminho = osrm_manager.garantir_grafo(oc, pasta_de_dados(), progresso=progresso)
    except Exception as e:
        logger.warning("[PROV] download do grafo falhou.", exc_info=True)
        return {"ok": False, "caminho": None, "detalhe": "erro: %s" % e}
    if caminho and os.path.exists(caminho):
        return {"ok": True, "caminho": caminho, "detalhe": "grafo pronto em %s" % caminho}
    return {"ok": False, "caminho": None, "detalhe": "não foi possível provisionar (verifique conexão)"}


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
