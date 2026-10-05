# -*- coding: utf-8 -*-
"""OpenRotas Desktop — registro e carregamento de DADOS LOCAIS (Etapa 4).

Gerencia os conjuntos de dados geográficos que vivem no disco (as bases embarcadas no projeto
+ dados grandes opcionais instalados à parte em data_local/). Entrega:

  • REGISTRO declarativo (nome, caminho, essencial?, formato) — §8/§33;
  • CARREGAMENTO PREGUIÇOSO + cache em memória — carrega só quando acessado (§16), e lê só as
    COLUNAS pedidas em Parquet (projeção) para não estourar RAM com arquivos grandes;
  • ÍNDICE O(1) de municípios por código IBGE — útil para geocodificação/validação offline;
  • INTEGRIDADE/VERSÃO — tamanho + hash parcial rápido, para o diagnóstico e a lógica de
    atualização incremental (§19: atualizar só o que mudou);
  • PRONTIDÃO OFFLINE — responde se o essencial para rodar sem internet está presente (§12).

Defensivo: acessores nunca levantam para o chamador casual (há variantes _try). Depende de
pandas/pyarrow, que já são dependências da aplicação."""
from __future__ import annotations

import os
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger("openrotas.desktop.data")


@dataclass(frozen=True)
class Dataset:
    chave: str
    rel: str            # caminho relativo à raiz do app
    essencial: bool
    formato: str        # parquet | pickle_gz | csv | shp_zip | osrm | outro
    descricao: str = ""


# Catálogo declarativo. As bases ESSENCIAIS vêm embarcadas no projeto; o grafo OSRM é opcional
# e instalado à parte (data_local/) — ver guias. Caminhos relativos à raiz do app.
CATALOGO = [
    Dataset("municipios", "data/brasil/ibge/derivadas/municipios.parquet", True, "parquet",
            "Municípios IBGE (código, nome, UF, centroide) — base da geocodificação local."),
    Dataset("massas_dagua", "data/brasil/ibge/derivadas/massas_dagua.parquet", True, "parquet",
            "Massas d'água (lagos/represas) — inteligência hidrográfica."),
    # Camadas NACIONAIS grandes (IBGE BC250/BC100), reassembladas de _bigparts/ no build — §12.
    Dataset("drenagem", "data/brasil/ibge/derivadas/drenagem.parquet", True, "parquet",
            "Rede de drenagem/rios nacional (~2,18 M trechos) — detecção fluvial de todo o Brasil."),
    Dataset("rodovias", "data/brasil/ibge/derivadas/rodovias.parquet", True, "parquet",
            "Malha rodoviária nacional (~287 k trechos) — contexto rodoviário de todo o Brasil."),
    Dataset("hidrografia_nacional", "hidrografia_nacional.pkl.gz", True, "pickle_gz",
            "Grafo/índice hidrográfico nacional."),
    # Camadas geoespaciais/aquaviárias complementares (nacional) — feições enriquecedoras.
    Dataset("ferrovias", "data/brasil/ibge/derivadas/ferrovias.parquet", False, "parquet",
            "Malha ferroviária nacional."),
    Dataset("pontes", "data/brasil/ibge/derivadas/pontes.parquet", False, "parquet",
            "Pontes (travessias rodoviárias sobre água)."),
    Dataset("travessias", "data/brasil/ibge/derivadas/travessias.parquet", False, "parquet",
            "Travessias/balsas."),
    Dataset("hidrovias", "data/brasil/ibge/derivadas/hidrovias.parquet", False, "parquet",
            "Hidrovias (rede aquaviária)."),
    Dataset("eclusas", "data/brasil/ibge/derivadas/eclusas.parquet", False, "parquet",
            "Eclusas."),
    Dataset("atracadouros_terminal", "data/brasil/ibge/derivadas/atracadouros_terminal.parquet", False, "parquet",
            "Atracadouros/terminais aquaviários."),
    Dataset("complexos_portuarios", "data/brasil/ibge/derivadas/complexos_portuarios.parquet", False, "parquet",
            "Complexos portuários."),
    Dataset("sinalizacao", "data/brasil/ibge/derivadas/sinalizacao.parquet", False, "parquet",
            "Sinalização náutica."),
    Dataset("rios_nomeados", "data/brasil/ibge/derivadas/rios_nomeados_index.parquet", False, "parquet",
            "Índice de rios nomeados (estação ANA mais próxima)."),
    Dataset("amazonia_fluvial", "amazonia_fluvial.pkl.gz", False, "pickle_gz",
            "Grafo fluvial amazônico."),
    Dataset("snirh_rios", "snirh_rios.csv", False, "csv", "Rios SNIRH."),
    # Opcional, instalado à parte (NÃO embarcado): grafo rodoviário OSRM do Brasil.
    Dataset("osrm_brasil", "data_local/brazil-latest.osrm", False, "osrm",
            "Grafo rodoviário OSRM do Brasil (roteamento local/offline) — instalado à parte."),
]
_POR_CHAVE = {d.chave: d for d in CATALOGO}


class LocalDataRegistry:
    """Registro com estado (cache em memória dos dataframes já carregados)."""

    def __init__(self, app_root: Path, data_local_dir: Path | None = None):
        self.app_root = Path(app_root)
        # data_local pode viver no perfil do usuário (fora da instalação) — §19.
        self.data_local_dir = Path(data_local_dir) if data_local_dir else (self.app_root / "data_local")
        # [REPARO/ATUALIZAÇÃO SEM REINSTALAR - §18/§19/§45] Diretório de OVERRIDE no perfil do
        # usuário: uma cópia reparada/atualizada de uma base aqui VENCE a embarcada no bundle
        # (que é read-only em Program Files). Assim dá para consertar/atualizar uma base sem
        # reinstalar o app inteiro.
        self.override_dir = self.data_local_dir.parent / "bases"
        self._cache: dict = {}

    # ---- resolução de caminho (override do usuário > bundle; osrm no data_local do usuário) ----
    def caminho(self, chave: str) -> Path:
        d = _POR_CHAVE[chave]
        if d.rel.startswith("data_local/"):
            return self.data_local_dir / d.rel.split("/", 1)[1]
        # override reparado/atualizado no perfil do usuário tem prioridade sobre o bundle
        try:
            ov = self.override_dir / os.path.basename(d.rel)
            if ov.exists():
                return ov
        except Exception:
            pass
        return self.app_root / d.rel

    def existe(self, chave: str) -> bool:
        try:
            return self.caminho(chave).exists()
        except Exception:
            return False

    # ---- carregamento preguiçoso ----
    def carregar_parquet(self, chave: str, colunas=None):
        """Carrega um Parquet sob demanda, com PROJEÇÃO de colunas (lê só o necessário — §16).
        Resultado cacheado por (chave, colunas). Levanta se faltar (uso interno)."""
        ck = (chave, tuple(colunas) if colunas else None)
        if ck in self._cache:
            return self._cache[ck]
        import pandas as pd
        df = pd.read_parquet(self.caminho(chave), columns=list(colunas) if colunas else None)
        self._cache[ck] = df
        return df

    def municipios(self, colunas=None):
        """DataFrame de municípios (lazy). Sem colunas → todas."""
        return self.carregar_parquet("municipios", colunas=colunas)

    def indice_municipios_por_ibge(self) -> dict:
        """Índice O(1) {codigo_ibge(str) -> dict da linha}. Detecta a coluna de código IBGE
        de forma robusta (nomes variam entre gerações). Cacheado. {} em falha."""
        if "_idx_ibge" in self._cache:
            return self._cache["_idx_ibge"]
        idx = {}
        try:
            df = self.municipios()
            col_ibge = next((c for c in df.columns
                             if str(c).lower() in ("geocodigo", "codigo_ibge", "cod_ibge", "ibge",
                                                   "cd_mun", "cd_geocmu", "codigo")), None)
            if col_ibge is not None:
                for rec in df.to_dict("records"):
                    idx[str(rec.get(col_ibge))] = rec
        except Exception:
            logger.warning("Falha ao indexar municípios por IBGE.", exc_info=True)
        self._cache["_idx_ibge"] = idx
        return idx

    def liberar_memoria(self):
        """Esvazia o cache em memória (os arquivos continuam no disco)."""
        self._cache.clear()

    # ---- integridade / versão (§17/§18/§19) ----
    def legivel(self, chave: str) -> bool:
        """Verifica BARATO se o arquivo realmente ABRE no formato esperado (não só existe):
        Parquet → lê o schema (rodapé, O(1)); pickle_gz → descomprime 1 KB; csv → lê 1 linha.
        Detecta corrupção que a checagem de existência não pega (§18). Nunca levanta."""
        try:
            d = _POR_CHAVE[chave]
            p = self.caminho(chave)
            if not p.exists():
                return False
            fmt = d.formato
            if fmt == "parquet":
                import pyarrow.parquet as pq
                pq.read_schema(str(p))                 # só o rodapé; não carrega os dados
                return True
            if fmt == "pickle_gz":
                import gzip
                with gzip.open(p, "rb") as f:
                    f.read(1024)
                return True
            if fmt == "csv":
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    f.readline()
                return True
            return True                                # osrm/outro: existência basta
        except Exception:
            logger.warning("Recurso %r não está legível (possível corrupção).", chave, exc_info=True)
            return False

    def assinatura(self, chave: str) -> dict:
        """Tamanho + hash parcial rápido (1º e último MB) — barato mesmo em arquivos de GB,
        suficiente para detectar troca de versão/corrupção sem ler o arquivo inteiro."""
        p = self.caminho(chave)
        try:
            tam = p.stat().st_size
            h = hashlib.sha256()
            with open(p, "rb") as f:
                h.update(f.read(1024 * 1024))          # 1º MB
                if tam > 2 * 1024 * 1024:
                    f.seek(-1024 * 1024, os.SEEK_END)
                    h.update(f.read(1024 * 1024))      # último MB
            return {"existe": True, "bytes": tam, "hash12": h.hexdigest()[:12]}
        except Exception:
            return {"existe": False, "bytes": 0, "hash12": ""}

    # ---- status / prontidão offline ----
    def status(self) -> list:
        linhas = []
        for d in CATALOGO:
            ok = self.existe(d.chave)
            info = {"chave": d.chave, "essencial": d.essencial, "existe": ok,
                    "caminho": str(self.caminho(d.chave)), "descricao": d.descricao}
            if ok:
                try:
                    info["mb"] = round(self.caminho(d.chave).stat().st_size / (1024 ** 2), 1)
                except Exception:
                    info["mb"] = None
            linhas.append(info)
        return linhas

    def essenciais_ok(self) -> bool:
        return all(self.existe(d.chave) for d in CATALOGO if d.essencial)

    def offline_pronto(self) -> dict:
        """Offline exige: bases essenciais (geocodificação/hidro local) + grafo rodoviário local
        (roteamento sem internet). Diz o que falta, se faltar."""
        tem_essenciais = self.essenciais_ok()
        tem_osrm = self.existe("osrm_brasil")
        faltam = []
        if not tem_essenciais:
            faltam += [d.chave for d in CATALOGO if d.essencial and not self.existe(d.chave)]
        if not tem_osrm:
            faltam.append("osrm_brasil (grafo rodoviário local)")
        return {"pronto": bool(tem_essenciais and tem_osrm),
                "geocodificacao_hidro_local": tem_essenciais,
                "roteamento_local": tem_osrm, "faltam": faltam}


def registry_padrao() -> "LocalDataRegistry":
    """Registry usando a raiz do app e o data_local no perfil do usuário (se existir)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    import desktop_config as cfg
    return LocalDataRegistry(cfg.app_root(), (cfg.user_data_dir() / "data_local"))
