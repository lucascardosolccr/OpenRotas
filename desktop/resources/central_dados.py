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
        root.title("OpenRotas — Central de Dados")
        root.geometry("640x460")
        root.minsize(560, 420)

        pad = {"padx": 16, "pady": 8}
        cab = ttk.Frame(root)
        cab.pack(fill="x", **pad)
        ttk.Label(cab, text="Central de Dados", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(cab, text="Baixe e instale todo o conteúdo do Brasil direto na pasta do app.",
                  foreground="#5b6676").pack(anchor="w")

        self.resumo = ttk.Label(root, text="", justify="left", font=("Segoe UI", 10))
        self.resumo.pack(fill="x", **pad)

        grafo = ttk.LabelFrame(root, text="Mapa de rotas do Brasil (grafo OSRM — roteamento offline)")
        grafo.pack(fill="x", **pad)
        self.estado_grafo = ttk.Label(grafo, text="", justify="left")
        self.estado_grafo.pack(anchor="w", padx=12, pady=(8, 4))
        self.btn_baixar = ttk.Button(grafo, text="Baixar o mapa do Brasil (~6,7 GB)",
                                     command=self._on_baixar_grafo)
        self.btn_baixar.pack(anchor="w", padx=12, pady=(0, 10))

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

        rod = ttk.Frame(root)
        rod.pack(fill="x", side="bottom", **pad)
        ttk.Button(rod, text="Reparar/instalar bases nacionais", command=self._on_reparar).pack(side="left")
        ttk.Button(rod, text="Abrir pasta de dados", command=self._on_abrir).pack(side="left", padx=8)
        ttk.Button(rod, text="Ativar roteamento local (Docker)",
                   command=self._on_ativar_local).pack(side="left")
        ttk.Button(rod, text="Fechar", command=root.destroy).pack(side="right")

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
            self.estado_grafo.config(text="Instalado ✓ — roteamento local disponível.")
            self.btn_baixar.config(state="disabled")
        else:
            self.estado_grafo.config(text="Ausente. Baixe uma vez para ter o Brasil inteiro offline.")
            self.btn_baixar.config(state=("disabled" if self._ocupado else "normal"))

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
                    if fase == "extraindo":
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
                    self._set_status(dado.get("detalhe", ""),
                                     "#1a7f4b" if dado.get("ok") else "#b42318")
                    self._travar(False)
                    self._atualizar_inventario()
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
