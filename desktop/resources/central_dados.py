# -*- coding: utf-8 -*-
"""OpenRotas Desktop — CENTRAL DE DADOS (janela nativa) — §12/§17/§32.

A OPÇÃO DENTRO DO SOFTWARE para baixar e instalar, com UM CLIQUE, TODO o conteúdo pesado que não
cabe no instalador — hoje o grafo rodoviário OSRM do Brasil (vários GB) — direto para a pasta de
dados que a aplicação usa. Também repara/atualiza as bases e abre a pasta de dados.

É um INVÓLUCRO FINO sobre `provisionamento.py` (onde mora toda a lógica, testada): aqui só há
Tkinter (biblioteca-padrão do Python, empacotada pelo PyInstaller — sem dependência nova). O
download roda numa THREAD; o progresso chega à UI por uma fila consumida via `after` (sem travar
a janela). Defensivo de ponta a ponta: se não houver Tkinter/display, cai para a versão de texto
(CLI) sem quebrar.

Abre por: OpenRotas.exe --central   (atalho "OpenRotas — Central de Dados" no menu Iniciar)."""
from __future__ import annotations

import os
import sys
import queue
import logging
import threading
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent / "app", _AQUI.parent, _AQUI.parent / "data_local", _AQUI.parent / "engines"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import provisionamento as prov  # noqa: E402

logger = logging.getLogger("openrotas.desktop.central")


def _tkinter_disponivel() -> bool:
    """Há Tkinter E uma sessão gráfica utilizável? (No CI/headless, não.)"""
    if os.name == "posix" and sys.platform != "darwin" and not os.environ.get("DISPLAY"):
        return False
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Fallback de TEXTO (sem GUI): mostra o inventário e baixa o grafo pela linha
# de comando, com progresso textual. Usado em headless ou se o Tk faltar.
# ---------------------------------------------------------------------------
def _resumo_texto() -> str:
    inv = prov.inventario()
    linhas = ["OpenRotas — Central de Dados (modo texto)", "=" * 48,
              "Pasta de dados: %s" % inv.get("pasta_dados", "?")]
    r = inv.get("resumo") or {}
    linhas.append("Recursos: %s instalados de %s." % (r.get("instalados", "?"), r.get("total", "?")))
    if r.get("faltam_obrigatorios"):
        linhas.append("  faltam (obrigatórios): %s" % ", ".join(r["faltam_obrigatorios"]))
    linhas.append("Grafo do Brasil (roteamento): %s"
                  % ("instalado ✓" if inv.get("grafo_instalado") else "AUSENTE (baixável, ~6,7 GB)"))
    return "\n".join(linhas)


def _executar_texto(baixar: bool) -> int:
    print(_resumo_texto())
    if not baixar:
        print("\nUse --central --baixar para baixar o grafo do Brasil agora (download único).")
        return 0
    if prov.grafo_instalado():
        print("\nO grafo do Brasil já está instalado. Nada a baixar.")
        return 0
    print("\nBaixando o grafo do Brasil (vários GB — download único)...")
    estado = {"ultimo": -1}

    def _prog(ev):
        if ev.get("fase") == "baixando":
            mb = int((ev.get("bytes") or 0) / (1024 * 1024))
            if mb - estado["ultimo"] >= 200:            # imprime a cada ~200 MB
                estado["ultimo"] = mb
                print("  baixado: %s" % prov.humano_bytes(ev.get("bytes") or 0))
        elif ev.get("fase") == "extraindo":
            print("  extraindo o pacote...")

    r = prov.baixar_grafo(progresso=_prog)
    print("  %s" % ("OK: %s" % r["caminho"] if r["ok"] else "falha: %s" % r["detalhe"]))
    return 0 if r["ok"] else 1


# ---------------------------------------------------------------------------
# GUI (Tkinter). Mantida pequena e defensiva; toda a lógica vem de provisionamento.
# ---------------------------------------------------------------------------
class _App:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root = root
        self.fila: "queue.Queue" = queue.Queue()
        self._ocupado = False
        self._ultimo_erro_grafo = ""     # motivo real da última falha de download (fase 'erro')
        self._auto_ativado = False       # garante a auto-ativação do roteamento só uma vez
        root.title("OpenRotas — Central de Dados")
        root.geometry("640x460")
        root.minsize(560, 420)

        pad = {"padx": 16, "pady": 8}
        cab = ttk.Frame(root)
        cab.pack(fill="x", **pad)
        ttk.Label(cab, text="Central de Dados", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(cab, text="Baixe e instale todo o conteúdo do Brasil direto na pasta do app.",
                  foreground="#5b6676").pack(anchor="w")
        # Versão visível: confirma qual build está instalado (ajuda a descartar instalador em cache).
        try:
            import desktop_config as _dc
            _ver = getattr(_dc, "APP_VERSION", "?")
        except Exception:
            _ver = "?"
        ttk.Label(cab, text="versão %s" % _ver, foreground="#8a93a0",
                  font=("Segoe UI", 8)).pack(anchor="w")
        # AVISO DE ATUALIZAÇÃO: aparece só quando há uma versão nova publicada (evita a confusão
        # de ficar numa versão antiga/instalador em cache). Preenchido em segundo plano.
        self.linha_update = ttk.Frame(cab)
        self.linha_update.pack(anchor="w", fill="x", pady=(2, 0))
        self.estado_update = ttk.Label(self.linha_update, text="", foreground="#1a7f4b")
        self.estado_update.pack(side="left")
        self.btn_update = ttk.Button(self.linha_update, text="Baixar atualização",
                                     command=self._on_baixar_update)
        # fica escondido até detectarmos nova versão (pack_forget)
        self._update_url = ""

        self.resumo = ttk.Label(root, text="", justify="left", font=("Segoe UI", 10))
        self.resumo.pack(fill="x", **pad)

        grafo = ttk.LabelFrame(root, text="Mapa de rotas do Brasil (grafo OSRM — roteamento offline)")
        grafo.pack(fill="x", **pad)
        self.estado_grafo = ttk.Label(grafo, text="", justify="left")
        self.estado_grafo.pack(anchor="w", padx=12, pady=(8, 4))
        self.btn_baixar = ttk.Button(grafo, text="Baixar o mapa do Brasil (~6,7 GB)",
                                     command=self._on_baixar_grafo)
        self.btn_baixar.pack(anchor="w", padx=12, pady=(0, 6))
        # ALTERNATIVA GARANTIDA: se o download dentro do app falhar (mas o navegador baixa normal),
        # o usuário baixa as partes pelo navegador e aponta a pasta — montagem 100% offline.
        alt = ttk.Frame(grafo)
        alt.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Label(alt, text="Não baixou pelo app? Baixe pelo navegador e importe:",
                  foreground="#5b6676").pack(anchor="w")
        linha_alt = ttk.Frame(alt)
        linha_alt.pack(fill="x", pady=(2, 0))
        ttk.Button(linha_alt, text="Abrir página de download",
                   command=self._on_abrir_pagina_download).pack(side="left")
        ttk.Button(linha_alt, text="Importar mapa de uma pasta…",
                   command=self._on_importar_local).pack(side="left", padx=8)

        # STATUS AO VIVO DO MOTOR DE ROTAS: mostra se as rotas estão indo pelo motor LOCAL
        # (rápido/offline) ou caindo no OSRM público (lento) — torna visível a falha silenciosa.
        motor_box = ttk.Frame(grafo)
        motor_box.pack(fill="x", padx=12, pady=(0, 10))
        self.estado_motor = ttk.Label(motor_box, text="Motor de rotas: verificando…",
                                      justify="left", foreground="#5b6676")
        self.estado_motor.pack(anchor="w")
        ttk.Button(motor_box, text="Testar motor de rotas",
                   command=self._on_testar_motor).pack(anchor="w", pady=(4, 0))

        # Dossiê de Rota por nome de cidade (integração total dos dados numa rota).
        dossie = ttk.LabelFrame(root, text="Dossiê de Rota (origem → destino, por cidade)")
        dossie.pack(fill="x", **pad)
        linha = ttk.Frame(dossie)
        linha.pack(fill="x", padx=12, pady=(8, 4))
        ttk.Label(linha, text="Origem:").pack(side="left")
        self.ent_origem = ttk.Entry(linha, width=22)
        self.ent_origem.insert(0, "São Paulo/SP")
        self.ent_origem.pack(side="left", padx=(4, 10))
        ttk.Label(linha, text="Destino:").pack(side="left")
        self.ent_destino = ttk.Entry(linha, width=22)
        self.ent_destino.insert(0, "Rio de Janeiro/RJ")
        self.ent_destino.pack(side="left", padx=4)
        ttk.Button(dossie, text="Gerar dossiê (HTML)", command=self._on_dossie).pack(anchor="w", padx=12, pady=(0, 10))

        self.barra = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.barra.pack(fill="x", **pad)
        self.status = ttk.Label(root, text="Pronto.", foreground="#5b6676")
        self.status.pack(fill="x", padx=16)
        # DESEMPENHO LOCAL (telemetria): tempo médio/p95 por rota — mostra o ganho do motor local.
        self.estado_perf = ttk.Label(root, text="", foreground="#5b6676", font=("Segoe UI", 8))
        self.estado_perf.pack(fill="x", padx=16)

        rod = ttk.Frame(root)
        rod.pack(fill="x", side="bottom", **pad)
        ttk.Button(rod, text="Reparar/instalar bases nacionais", command=self._on_reparar).pack(side="left")
        ttk.Button(rod, text="Abrir pasta de dados", command=self._on_abrir).pack(side="left", padx=8)
        ttk.Button(rod, text="Ativar roteamento local (rápido, sem Docker)",
                   command=self._on_ativar_local).pack(side="left")
        ttk.Button(rod, text="Diagnóstico completo", command=self._on_diagnostico).pack(side="left", padx=8)
        ttk.Button(rod, text="Fechar", command=root.destroy).pack(side="right")

        # Segunda linha de utilidades: integridade das bases + atalhos para as pastas do app.
        rod2 = ttk.Frame(root)
        rod2.pack(fill="x", side="bottom", padx=16, pady=(0, 2))
        ttk.Button(rod2, text="Verificar integridade das bases",
                   command=self._on_verificar_integridade).pack(side="left")
        ttk.Button(rod2, text="Abrir Downloads",
                   command=lambda: self._on_abrir_pasta("downloads")).pack(side="left", padx=8)
        ttk.Button(rod2, text="Abrir exports",
                   command=lambda: self._on_abrir_pasta("exports")).pack(side="left")
        ttk.Button(rod2, text="Abrir logs",
                   command=lambda: self._on_abrir_pasta("logs")).pack(side="left", padx=8)
        ttk.Button(rod2, text="Saúde Nacional dos dados",
                   command=self._on_saude_nacional).pack(side="left")

        self._atualizar_inventario()
        self.root.after(150, self._bombear_fila)

    # ---- helpers de UI ----
    def _set_status(self, txt, cor="#5b6676"):
        self.status.config(text=txt, foreground=cor)

    def _atualizar_inventario(self):
        inv = prov.inventario()
        r = inv.get("resumo") or {}
        self.resumo.config(text="Pasta de dados: %s\nRecursos: %s de %s instalados."
                           % (inv.get("pasta_dados", "?"), r.get("instalados", "?"), r.get("total", "?")))
        if inv.get("grafo_instalado"):
            # O mapa JÁ está na máquina → nada a baixar (botão desabilitado de propósito).
            self.btn_baixar.config(state="disabled")
            if not self._auto_ativado and not prov.roteamento_local_ativo():
                # TURNKEY/RECUPERAÇÃO: o grafo está presente mas o roteamento ficou 'off' (ex.: foi
                # extraído num clique que um bug antigo reportou como falha, então a ativação
                # automática nunca rodou). Liga sozinho — uma única vez — sem o usuário fazer nada.
                self._auto_ativado = True
                self.estado_grafo.config(text="Instalado ✓ — ligando o roteamento local…")
                threading.Thread(target=self._thread_ativar_auto, daemon=True).start()
            else:
                self.estado_grafo.config(
                    text="Instalado ✓ — roteamento local disponível (reabra o app para ativar).")
        else:
            self.estado_grafo.config(text="Ausente. Baixe uma vez para ter o Brasil inteiro offline.")
            self.btn_baixar.config(state=("disabled" if self._ocupado else "normal"))
        # Atualiza o status AO VIVO do motor de rotas (ping no 127.0.0.1) em segundo plano.
        threading.Thread(target=self._thread_status_motor, daemon=True).start()
        # Checa atualização do app e o desempenho local — ambos em segundo plano (podem fazer rede).
        threading.Thread(target=self._thread_update, daemon=True).start()
        threading.Thread(target=self._thread_perf, daemon=True).start()

    def _thread_update(self):
        try:
            u = prov.checar_atualizacao()
        except Exception as e:
            u = {"ha_atualizacao": False, "disponivel": False, "detalhe": "erro: %s" % e}
        self.fila.put(("update_status", u))

    def _thread_perf(self):
        try:
            p = prov.resumo_desempenho()
        except Exception as e:
            p = {"texto": "desempenho indisponível: %s" % e}
        self.fila.put(("perf_status", p))

    def _on_baixar_update(self):
        """Abre o instalador/página da nova versão no navegador do sistema."""
        import webbrowser
        url = self._update_url or "https://github.com/lucascardosolccr/OpenRotas/releases/tag/desktop-latest"
        try:
            webbrowser.open(url)
            self._set_status("Baixando a atualização pelo navegador… instale o .exe quando terminar.", "#1a7f4b")
        except Exception as e:
            self._set_status("Não consegui abrir o navegador: %s" % e, "#b42318")

    def _on_diagnostico(self):
        """Abre uma janela com o autodiagnóstico completo (bases, offline, motor, desempenho)."""
        self._set_status("Gerando diagnóstico…")
        threading.Thread(target=self._thread_diagnostico, daemon=True).start()

    def _thread_diagnostico(self):
        try:
            txt = prov.relatorio_diagnostico()
        except Exception as e:
            txt = "Falha ao gerar o diagnóstico: %s" % e
        self.fila.put(("diagnostico_fim", txt))

    def _mostrar_diagnostico(self, texto):
        """Janela de texto rolável (somente leitura) com o relatório de diagnóstico."""
        try:
            tk, ttk = self.tk, self.ttk
            top = tk.Toplevel(self.root)
            top.title("OpenRotas — Diagnóstico")
            top.geometry("720x560")
            quadro = ttk.Frame(top)
            quadro.pack(fill="both", expand=True, padx=12, pady=12)
            sb = ttk.Scrollbar(quadro, orient="vertical")
            txt = tk.Text(quadro, wrap="word", yscrollcommand=sb.set,
                          font=("Consolas", 9), background="#0E1117", foreground="#F9FAFB",
                          insertbackground="#F9FAFB", relief="flat")
            sb.config(command=txt.yview)
            sb.pack(side="right", fill="y")
            txt.pack(side="left", fill="both", expand=True)
            txt.insert("1.0", texto or "(sem conteúdo)")
            txt.config(state="disabled")
            ttk.Button(top, text="Fechar", command=top.destroy).pack(pady=(0, 10))
        except Exception as e:
            self._set_status("Diagnóstico pronto, mas não consegui abrir a janela: %s" % e, "#b42318")

    def _on_abrir_pasta(self, tipo):
        try:
            ok = prov.abrir_pasta_dados(prov.pasta_por_tipo(tipo))
            if not ok:
                self._set_status("Pasta: %s" % prov.pasta_por_tipo(tipo), "#5b6676")
        except Exception as e:
            self._set_status("Não consegui abrir a pasta: %s" % e, "#b42318")

    def _on_saude_nacional(self):
        self._set_status("Avaliando a saúde nacional dos dados…")
        threading.Thread(target=self._thread_saude, daemon=True).start()

    def _thread_saude(self):
        try:
            txt = prov.saude_nacional_texto(rapido=True)
        except Exception as e:
            txt = "Falha ao avaliar a saúde nacional: %s" % e
        self.fila.put(("saude_fim", txt))

    def _on_verificar_integridade(self):
        self._set_status("Verificando integridade das bases…")
        threading.Thread(target=self._thread_integridade, daemon=True).start()

    def _thread_integridade(self):
        try:
            r = prov.verificar_integridade()
        except Exception as e:
            r = {"ok": False, "detalhe": "falha: %s" % e}
        self.fila.put(("integridade_fim", r))

    def _on_testar_motor(self):
        try:
            self.estado_motor.config(text="Motor de rotas: testando…", foreground="#5b6676")
        except Exception:
            pass
        threading.Thread(target=self._thread_status_motor, daemon=True).start()

    def _thread_status_motor(self):
        try:
            st = prov.status_motor_rotas()
        except Exception as e:
            st = {"local_no_ar": False, "detalhe": "falha ao testar: %s" % e}
        self.fila.put(("motor_status", st))

    def _travar(self, travar: bool):
        self._ocupado = travar
        estado = "disabled" if travar else "normal"
        try:
            self.btn_baixar.config(state=estado)
        except Exception:
            pass

    # ---- ações (rodam em thread; progresso volta pela fila) ----
    def _on_baixar_grafo(self):
        if self._ocupado:
            return
        self._ultimo_erro_grafo = ""     # zera o motivo da tentativa anterior
        self._travar(True)
        self.barra.config(mode="indeterminate")
        self.barra.start(12)
        self._set_status("Baixando o mapa do Brasil (download único, pode demorar)...")
        threading.Thread(target=self._thread_baixar, daemon=True).start()

    def _thread_baixar(self):
        def _prog(ev):
            self.fila.put(("grafo", ev))
        r = prov.baixar_grafo(progresso=_prog)
        self.fila.put(("grafo_fim", r))

    def _thread_ativar_auto(self):
        """Liga o roteamento local em segundo plano (não trava a janela). Resultado volta pela fila."""
        try:
            r = prov.ativar_roteamento_local()
        except Exception as e:
            r = {"ok": False, "detalhe": "erro: %s" % e}
        self.fila.put(("auto_ativar_fim", r))

    def _on_abrir_pagina_download(self):
        """Abre, no navegador do sistema, a página de download das partes do mapa."""
        try:
            import webbrowser
            webbrowser.open("https://github.com/lucascardosolccr/OpenRotas/releases/tag/osrm-brasil-latest")
            self._set_status("Baixe no navegador os arquivos 'brazil-osrm-mld.tar.gz.part00/01/02' "
                             "para uma pasta e use 'Importar mapa de uma pasta…'.")
        except Exception as e:
            self._set_status("Não consegui abrir o navegador: %s" % e, "#b42318")

    def _on_importar_local(self):
        """Pede uma pasta com as partes baixadas pelo navegador e monta o mapa offline (sem rede)."""
        if self._ocupado:
            return
        from tkinter import filedialog
        pasta = filedialog.askdirectory(title="Pasta com os arquivos do mapa (brazil-osrm-mld.tar.gz.part*)")
        if not pasta:
            return
        self._ultimo_erro_grafo = ""
        self._travar(True)
        self.barra.config(mode="indeterminate")
        self.barra.start(12)
        self._set_status("Montando o mapa a partir da pasta (offline)...")
        threading.Thread(target=self._thread_importar, args=(pasta,), daemon=True).start()

    def _thread_importar(self, pasta):
        def _prog(ev):
            self.fila.put(("grafo", ev))
        r = prov.importar_grafo_de_pasta(pasta, progresso=_prog)
        self.fila.put(("grafo_fim", r))

    def _on_reparar(self):
        if self._ocupado:
            return
        self._travar(True)
        self._set_status("Reparando/atualizando bases...")
        threading.Thread(target=lambda: self.fila.put(("reparo_fim", prov.reparar_bases())),
                         daemon=True).start()

    def _on_ativar_local(self):
        r = prov.ativar_roteamento_local()
        self._set_status(r.get("detalhe", ""), "#1a7f4b" if r.get("ok") else "#b42318")

    def _on_abrir(self):
        prov.abrir_pasta_dados()

    def _on_dossie(self):
        if self._ocupado:
            return
        origem = self.ent_origem.get().strip()
        destino = self.ent_destino.get().strip()
        if not origem or not destino:
            self._set_status("Informe origem e destino.", "#b42318")
            return
        self._travar(True)
        self._set_status("Gerando dossiê %s → %s..." % (origem, destino))
        threading.Thread(target=self._thread_dossie, args=(origem, destino), daemon=True).start()

    def _thread_dossie(self, origem, destino):
        try:
            from geo import dossie_rota
            dd, _ = dossie_rota.dossie_por_nomes([origem, destino])
            if dd.get("erro"):
                self.fila.put(("dossie_fim", {"ok": False, "detalhe": dd["erro"]}))
                return
            destino_html = prov.pasta_de_dados().parent / "exports" / "dossie_rota.html"
            got = dossie_rota.gerar_html(dd, destino_html)
            if got:
                try:
                    prov.abrir_pasta_dados(Path(got).parent)
                except Exception:
                    pass
            self.fila.put(("dossie_fim", {"ok": bool(got), "caminho": got}))
        except Exception as e:
            self.fila.put(("dossie_fim", {"ok": False, "detalhe": str(e)}))

    # ---- consumidor da fila (thread-safe via after) ----
    def _bombear_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "grafo":
                    fase = (dado or {}).get("fase")
                    b = (dado or {}).get("bytes") or 0
                    if fase == "erro":
                        # MOTIVO REAL da falha (rede/TLS/servidor/integridade) — guarda para compor
                        # a mensagem final em vez do texto genérico.
                        self._ultimo_erro_grafo = (dado or {}).get("detalhe") or ""
                        self._set_status("Problema no download: %s" % self._ultimo_erro_grafo, "#b42318")
                    elif fase == "extraindo":
                        self._set_status("Extraindo o pacote do grafo...")
                    elif fase == "concatenando":
                        self._set_status("Concatenando %s parte(s)..." % (dado or {}).get("partes", "?"))
                    elif b:
                        txt = "Baixando: %s" % prov.humano_bytes(b)
                        if (dado or {}).get("parte") is not None:
                            txt += " (parte %02d)" % dado["parte"]
                        if (dado or {}).get("velocidade_bps"):
                            txt += " · %s" % prov.humano_velocidade(dado["velocidade_bps"])
                        if (dado or {}).get("eta_s") not in (None, -1):
                            txt += " · ETA %s" % prov.humano_eta(dado["eta_s"])
                        self._set_status(txt)
                elif tipo == "grafo_fim":
                    self.barra.stop()
                    self.barra.config(mode="determinate", value=(100 if dado.get("ok") else 0))
                    if dado.get("ok"):
                        # Turnkey: assim que o mapa chega, LIGA o roteamento local sozinho (modo
                        # 'auto' → motor nativo embarcado, sem Docker). O usuário não precisa de mais
                        # nenhum passo — o próximo estudo já roda rápido e offline.
                        try:
                            r = prov.ativar_roteamento_local()
                            self._set_status("Mapa instalado ✓ — " + r.get("detalhe", "roteamento local ligado."),
                                             "#1a7f4b")
                        except Exception:
                            self._set_status(dado.get("detalhe", "Mapa instalado ✓"), "#1a7f4b")
                    else:
                        # Junta o motivo REAL capturado durante o download (fase 'erro') à mensagem
                        # final — assim o usuário (e o suporte) vê a causa, não só o texto genérico.
                        _base = dado.get("detalhe", "")
                        _causa = getattr(self, "_ultimo_erro_grafo", "")
                        _msg = ("%s  [causa: %s]" % (_base, _causa)) if _causa else _base
                        self._set_status(_msg, "#b42318")
                    self._travar(False)
                    self._atualizar_inventario()
                elif tipo == "motor_status":
                    _noar = bool((dado or {}).get("local_no_ar"))
                    _txt = "Motor de rotas: %s" % (dado or {}).get("detalhe", "?")
                    self.estado_motor.config(text=_txt, foreground=("#1a7f4b" if _noar else "#9a6700"))
                elif tipo == "update_status":
                    d = dado or {}
                    if d.get("ha_atualizacao") and d.get("url_instalador"):
                        self._update_url = d.get("url_instalador") or ""
                        self.estado_update.config(
                            text="↑ Nova versão %s disponível (você tem %s)."
                                 % (d.get("remota", "?"), d.get("atual", "?")), foreground="#1a7f4b")
                        try:
                            self.btn_update.pack(side="left", padx=8)
                        except Exception:
                            pass
                    else:
                        self.estado_update.config(text="")
                        try:
                            self.btn_update.pack_forget()
                        except Exception:
                            pass
                elif tipo == "perf_status":
                    self.estado_perf.config(text=(dado or {}).get("texto", ""))
                elif tipo == "integridade_fim":
                    _ok = bool((dado or {}).get("ok"))
                    self._set_status("Integridade: %s" % (dado or {}).get("detalhe", "?"),
                                     "#1a7f4b" if _ok else "#9a6700")
                    self._atualizar_inventario()
                elif tipo == "diagnostico_fim":
                    self._set_status("Diagnóstico pronto.", "#1a7f4b")
                    self._mostrar_diagnostico(dado)
                elif tipo == "saude_fim":
                    self._set_status("Saúde nacional avaliada.", "#1a7f4b")
                    self._mostrar_diagnostico(dado)
                elif tipo == "auto_ativar_fim":
                    if dado.get("ok"):
                        self.estado_grafo.config(
                            text="Instalado ✓ — " + dado.get("detalhe", "roteamento local ligado."))
                        self._set_status("Roteamento local ligado automaticamente. "
                                         "Reabra o app para o motor local entrar no ar.", "#1a7f4b")
                    else:
                        self.estado_grafo.config(text="Instalado ✓ — roteamento local disponível.")
                elif tipo == "dossie_fim":
                    if dado.get("ok"):
                        self._set_status("Dossiê gerado: %s" % dado.get("caminho", ""), "#1a7f4b")
                    else:
                        self._set_status("Dossiê: %s" % dado.get("detalhe", "falha"), "#b42318")
                    self._travar(False)
                elif tipo == "reparo_fim":
                    ok = bool((dado or {}).get("ok"))
                    self._set_status("Bases: %s" % ("tudo OK ✓" if ok else "ver detalhes/log"),
                                     "#1a7f4b" if ok else "#9a6700")
                    self._travar(False)
                    self._atualizar_inventario()
        except queue.Empty:
            pass
        self.root.after(200, self._bombear_fila)


def abrir_gui() -> int:
    """Abre a janela da Central de Dados. Devolve 0 ao fechar; 2 se o Tk não estiver disponível."""
    try:
        import tkinter as tk
    except Exception:
        return 2
    try:
        root = tk.Tk()
        _App(root)
        root.mainloop()
        return 0
    except Exception:
        logger.warning("[CENTRAL] falha ao abrir a GUI; caindo para o modo texto.", exc_info=True)
        return 2


def main(argv=None) -> int:
    """Ponto de entrada. GUI quando possível; senão, modo texto. `--baixar` (modo texto) baixa já."""
    argv = argv if argv is not None else sys.argv[1:]
    if _tkinter_disponivel():
        rc = abrir_gui()
        if rc != 2:
            return rc
    return _executar_texto(baixar=("--baixar" in argv))


if __name__ == "__main__":
    raise SystemExit(main())
