# -*- coding: utf-8 -*-
"""Testes reais e offline de auth/validators.py — nenhum aqui toca rede/banco."""
from auth import validators as v


# ==============================================================================
# Nome
# ==============================================================================

def test_validar_nome_valido_aceita_e_capitaliza():
    ok, nome, _ = v.validar_nome("joão da silva")
    assert ok
    assert nome == "João da Silva"


def test_validar_nome_vazio_e_invalido():
    ok, _, motivo = v.validar_nome("")
    assert not ok and motivo


def test_validar_nome_none_e_invalido():
    ok, _, motivo = v.validar_nome(None)
    assert not ok and "obrigatório" in motivo.lower()


def test_validar_nome_sem_sobrenome_e_invalido():
    ok, _, motivo = v.validar_nome("Maria")
    assert not ok
    assert "sobrenome" in motivo.lower()


def test_validar_nome_com_digitos_e_invalido():
    ok, _, _ = v.validar_nome("Jo4o Silva")
    assert not ok


def test_validar_nome_com_hifen_e_apostrofo_e_valido():
    ok, nome, _ = v.validar_nome("Maria-José D'Ávila")
    assert ok
    assert "D'Ávila" in nome or "D'ávila" in nome  # capitalize() de "d'ávila" -> "D'ávila"


def test_validar_nome_colapsa_espacos_multiplos():
    ok, nome, _ = v.validar_nome("  João   Silva  ")
    assert ok
    assert nome == "João Silva"


def test_validar_nome_iniciais_soltas_sao_suspeitas():
    ok, _, motivo = v.validar_nome("A B")
    assert not ok


# ==============================================================================
# E-mail
# ==============================================================================

def test_validar_email_valido_normaliza_minusculas():
    ok, email, _ = v.validar_email("Usuario@Exemplo.COM")
    assert ok
    assert email == "usuario@exemplo.com"


def test_validar_email_sem_arroba_e_invalido():
    ok, _, motivo = v.validar_email("usuario.exemplo.com")
    assert not ok


def test_validar_email_sem_dominio_e_invalido():
    ok, _, _ = v.validar_email("usuario@exemplo")
    assert not ok


def test_validar_email_vazio_e_invalido():
    ok, _, _ = v.validar_email("   ")
    assert not ok


def test_validar_email_pontos_duplicados_e_invalido():
    ok, _, _ = v.validar_email("usuario..nome@exemplo.com")
    assert not ok


def test_validar_email_com_espacos_nas_bordas_normaliza():
    ok, email, _ = v.validar_email("  usuario@exemplo.com  ")
    assert ok
    assert email == "usuario@exemplo.com"


# ==============================================================================
# Telefone
# ==============================================================================

def test_validar_telefone_celular_valido():
    ok, tel, _ = v.validar_telefone("(11) 98765-4321")
    assert ok
    assert tel == "+5511987654321"


def test_validar_telefone_fixo_valido():
    ok, tel, _ = v.validar_telefone("(21) 3333-4444")
    assert ok
    assert tel == "+552133334444"


def test_validar_telefone_ja_com_codigo_pais():
    ok, tel, _ = v.validar_telefone("+55 11 98765-4321")
    assert ok
    assert tel == "+5511987654321"


def test_validar_telefone_ddd_invalido():
    ok, _, motivo = v.validar_telefone("(01) 98765-4321")
    assert not ok


def test_validar_telefone_celular_sem_9_inicial_e_invalido():
    # 11 dígitos: DDD 11 + número de 9 dígitos começando com 8 (não com 9).
    ok, _, motivo = v.validar_telefone("11876543219")
    assert not ok
    assert "9" in motivo


def test_validar_telefone_curto_demais_e_invalido():
    ok, _, _ = v.validar_telefone("11987")
    assert not ok


def test_formatar_telefone_exibicao_celular():
    assert v.formatar_telefone_exibicao("+5511987654321") == "(11) 98765-4321"


def test_formatar_telefone_exibicao_fixo():
    assert v.formatar_telefone_exibicao("+552133334444") == "(21) 3333-4444"


def test_formatar_telefone_exibicao_entrada_invalida_nao_lanca():
    assert v.formatar_telefone_exibicao("abc") == "abc"
    assert v.formatar_telefone_exibicao(None) == ""


# ==============================================================================
# CEP / UF / Endereço
# ==============================================================================

def test_validar_cep_valido():
    ok, cep, _ = v.validar_cep("70040020")
    assert ok
    assert cep == "70040-020"


def test_validar_cep_com_mascara_valido():
    ok, cep, _ = v.validar_cep("70040-020")
    assert ok
    assert cep == "70040-020"


def test_validar_cep_invalido():
    ok, _, _ = v.validar_cep("123")
    assert not ok


def test_validar_uf_valida():
    ok, uf, _ = v.validar_uf("go")
    assert ok
    assert uf == "GO"


def test_validar_uf_invalida():
    ok, _, _ = v.validar_uf("XX")
    assert not ok


def test_validar_endereco_completo_valido():
    ok, dados, erros = v.validar_endereco(
        "SQN 100", "Bloco A", "Asa Norte", "Brasília", "df", "70040020")
    assert ok
    assert erros == []
    assert dados["uf"] == "DF"
    assert dados["cep"] == "70040-020"


def test_validar_endereco_campos_faltando_acumula_erros():
    ok, dados, erros = v.validar_endereco("", "", "", "", "XX", "123")
    assert not ok
    assert dados is None
    assert len(erros) >= 4  # logradouro, numero, bairro, cidade (+ uf + cep)


# ==============================================================================
# Senha
# ==============================================================================

def test_validar_forca_senha_forte():
    ok, _, nivel = v.validar_forca_senha("C0rreto!Cavalo#Bateria")
    assert ok
    assert nivel in ("media", "forte")


def test_validar_forca_senha_curta_e_invalida():
    ok, motivo, _ = v.validar_forca_senha("Ab1!")
    assert not ok
    assert "curta" in motivo.lower()


def test_validar_forca_senha_so_letras_minusculas_e_invalida():
    ok, motivo, _ = v.validar_forca_senha("abcdefghijk")
    assert not ok


def test_validar_forca_senha_trivial_e_invalida():
    ok, motivo, _ = v.validar_forca_senha("12345678")
    assert not ok
    assert "comum" in motivo.lower()


def test_validar_forca_senha_none_e_invalida():
    ok, motivo, _ = v.validar_forca_senha(None)
    assert not ok


def test_validar_forca_senha_excede_tamanho_maximo():
    ok, motivo, _ = v.validar_forca_senha("Aa1!" * 40)  # 160 chars
    assert not ok
    assert "máximo" in motivo.lower()


def test_validar_forca_senha_retrocompativel_sem_contexto():
    # Chamada antiga (só a senha) continua funcionando igual.
    ok, _, _ = v.validar_forca_senha("C0rreto!Cavalo#Bateria")
    assert ok


def test_validar_forca_senha_rejeita_conter_email():
    # Uma senha que passaria nas classes, mas contém o começo do e-mail, é recusada.
    ok, motivo, _ = v.validar_forca_senha("Joao.silva@2024", email="joao.silva@exemplo.com")
    assert not ok
    assert "e-mail" in motivo.lower()


def test_validar_forca_senha_rejeita_conter_nome():
    ok, motivo, _ = v.validar_forca_senha("Fernanda#2024", nome="Fernanda Souza")
    assert not ok
    assert "nome" in motivo.lower()


def test_validar_forca_senha_nome_curto_nao_gera_falso_positivo():
    # Tokens de nome com <4 caracteres não bloqueiam (ex.: "Ana", "Sá").
    ok, _, _ = v.validar_forca_senha("Trib0!Xy#Kw9", nome="Ana Sá")
    assert ok


def test_validar_forca_senha_novo_trivial_que_passa_classes():
    # "Senha@123" passa nas 3 classes, mas é comum — deve cair na lista de triviais.
    ok, motivo, _ = v.validar_forca_senha("Senha@123")
    assert not ok
    assert "comum" in motivo.lower()


def test_senhas_conferem_iguais():
    assert v.senhas_conferem("MinhaSenha123!", "MinhaSenha123!") is True


def test_senhas_conferem_diferentes():
    assert v.senhas_conferem("MinhaSenha123!", "OutraSenha456@") is False


def test_senhas_conferem_none_e_falso():
    assert v.senhas_conferem(None, "x") is False
    assert v.senhas_conferem("x", None) is False


# ==============================================================================
# OTP
# ==============================================================================

def test_validar_formato_otp_valido():
    ok, codigo, _ = v.validar_formato_otp("123456")
    assert ok
    assert codigo == "123456"


def test_validar_formato_otp_com_espacos():
    ok, codigo, _ = v.validar_formato_otp(" 123 456 ")
    assert ok
    assert codigo == "123456"


def test_validar_formato_otp_tamanho_errado_e_invalido():
    ok, _, _ = v.validar_formato_otp("12345")
    assert not ok


def test_validar_formato_otp_none_e_invalido():
    ok, _, motivo = v.validar_formato_otp(None)
    assert not ok
