# -*- coding: utf-8 -*-
"""[CONGRUÊNCIA · Hidrografia + Geoespacial IBGE] Duas incongruências reais corrigidas:

1) A amostra de BACIAS listava só 10 "bacias" e MISTURAVA nomes oficiais com rótulos inexistentes
   ('Sudeste', 'Nordeste Oriental', 'Nordeste Setentrional'). O Brasil tem 12 REGIÕES HIDROGRÁFICAS
   oficiais (ANA/CNRH nº 32/2003). Agora são as 12 corretas, com coluna `fonte`.

2) A legenda de cobertura BC100 estava hard-coded e OMITIA a Bahia (a fonte `bcal` mapeia para BA).
   Agora o rótulo é DERIVADO do manifest, então nunca mente sobre o que há em disco."""
import streamlit_app as m


# ---- (1) Bacias: 12 regiões hidrográficas oficiais -----------------------------------------
def test_bacias_amostra_tem_as_12_regioes_oficiais():
    df = m._gerar_dados_bacias_fallback()
    assert len(df) == 12, "o Brasil tem 12 regiões hidrográficas oficiais (ANA/CNRH 32/2003)"
    nomes = set(df["nome"])
    # nomes oficiais que faltavam antes
    for oficial in ["Atlântico Nordeste Ocidental", "Atlântico Nordeste Oriental",
                    "Atlântico Leste", "Atlântico Sudeste", "Atlântico Sul"]:
        assert oficial in nomes, f"faltou região oficial: {oficial}"
    # rótulos inventados que NÃO podem mais existir
    for invento in ["Sudeste", "Nordeste Oriental", "Nordeste Setentrional"]:
        assert invento not in nomes, f"rótulo não-oficial ainda presente: {invento}"


def test_bacias_amostra_marca_a_fonte():
    df = m._gerar_dados_bacias_fallback()
    assert "fonte" in df.columns
    assert "ANA" in str(df["fonte"].iloc[0])
    assert df["fonte"].nunique() == 1


def test_bacias_amostra_areas_plausiveis():
    df = m._gerar_dados_bacias_fallback()
    # a Amazônica é de longe a maior; o total nacional ~8,5 milhões km²
    assert df.loc[df["nome"] == "Amazônica", "area_km2"].iloc[0] > 3_000_000
    assert 7_500_000 < int(df["area_km2"].sum()) < 9_000_000


# ---- (2) Rótulo BC100 derivado do manifest (inclui a Bahia) ---------------------------------
def test_rotulo_bc100_inclui_bahia_e_conta_certo():
    mani = {"fontes": {"bc100": {"ufs": {
        "acre": {}, "alagoas": {}, "bcal": {}, "espirito_santo": {},
        "go_df": {}, "rio_grande_do_sul": {}, "roraima": {}, "sergipe": {}}}}}
    rot, n = m._rotulo_bc100_ufs(mani)
    assert n == 8
    assert "BA" in rot, "a Bahia (fonte 'bcal') era omitida — não pode mais"
    assert "RR" in rot and "GO/DF" in rot


def test_rotulo_bc100_fail_open_sem_manifest():
    assert m._rotulo_bc100_ufs(None) == ("", 0)
    assert m._rotulo_bc100_ufs({}) == ("", 0)
    assert m._rotulo_bc100_ufs({"fontes": {"bc100": {"ufs": {}}}}) == ("", 0)


def test_rotulo_bc100_fonte_desconhecida_nao_e_fabricada():
    # uma fonte nova sem mapa aparece com o próprio nome (honesto), não é descartada nem inventada
    rot, n = m._rotulo_bc100_ufs({"fontes": {"bc100": {"ufs": {"acre": {}, "parana": {}}}}})
    assert n == 2
    assert "AC" in rot and "PARANA" in rot
