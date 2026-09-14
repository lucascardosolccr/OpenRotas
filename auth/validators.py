# -*- coding: utf-8 -*-
"""Validação e normalização de dados de cadastro/perfil — PURO, sem I/O.

Nenhuma função aqui toca rede, banco ou Streamlit: todas recebem uma string e devolvem
(ok: bool, valor_normalizado_ou_None, motivo: str). Isso as torna 100% testáveis offline
(inclusive neste ambiente sandbox, sem acesso ao Supabase) e reutilizáveis tanto no
formulário de cadastro quanto na edição de perfil, sem duplicar regra de negócio.
"""
import re
import unicodedata

# ==============================================================================
# Nome completo
# ==============================================================================

_NOME_MIN_LEN = 3
# Letras (com acentos), espaço, apóstrofo (D'Ávila) e hífen (Maria-José) — nunca dígitos/símbolos.
_NOME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'\- ]*[A-Za-zÀ-ÖØ-öø-ÿ]$")


def validar_nome(nome: str):
    """Nome completo: obrigatório, >=2 palavras (nome + sobrenome), sem dígitos/símbolos,
    aceita acentos/hífen/apóstrofo. Normaliza espaços múltiplos e capitaliza cada palavra."""
    if nome is None:
        return False, None, "Nome é obrigatório."
    _n = " ".join(str(nome).split())  # colapsa espaços múltiplos/bordas
    if len(_n) < _NOME_MIN_LEN:
        return False, None, f"Nome muito curto (mínimo {_NOME_MIN_LEN} caracteres)."
    if not _NOME_RE.match(_n):
        return False, None, "Nome contém caracteres inválidos (use apenas letras, espaço, hífen ou apóstrofo)."
    _partes = _n.split(" ")
    if len(_partes) < 2:
        return False, None, "Informe nome e sobrenome completos."
    if any(len(p) < 2 for p in _partes if p not in ("da", "de", "do", "das", "dos", "e")):
        # partículas curtas ("de", "da"...) são válidas mesmo com <2 letras; qualquer outra
        # palavra de 1 letra é suspeita (evita "A B C" passando como nome).
        _suspeitas = [p for p in _partes if len(p) < 2 and p.lower() not in
                      ("da", "de", "do", "das", "dos", "e")]
        if _suspeitas:
            return False, None, "Nome parece incompleto — confira se digitou corretamente."
    _capitalizado = " ".join(
        p if p.lower() in ("da", "de", "do", "das", "dos", "e") else p.capitalize()
        for p in _partes
    )
    return True, _capitalizado, ""


# ==============================================================================
# E-mail
# ==============================================================================

# RFC 5322 simplificado — suficiente para rejeitar erros de digitação comuns sem ser
# excessivamente restritivo (não tenta validar contra a lista completa da RFC).
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validar_email(email: str):
    """E-mail: obrigatório, formato válido, normalizado para minúsculas sem espaços nas
    bordas (a normalização é o que garante unicidade real — 'A@B.com' e 'a@b.com' são a
    MESMA conta)."""
    if email is None:
        return False, None, "E-mail é obrigatório."
    _e = str(email).strip().lower()
    if not _e:
        return False, None, "E-mail é obrigatório."
    if not _EMAIL_RE.match(_e):
        return False, None, "Formato de e-mail inválido."
    if ".." in _e or _e.startswith(".") or _e.endswith("."):
        return False, None, "Formato de e-mail inválido."
    return True, _e, ""


# ==============================================================================
# Telefone (padrão brasileiro, com DDD)
# ==============================================================================

def validar_telefone(telefone: str):
    """Telefone brasileiro: extrai só os dígitos, exige DDD (2 dígitos, 11-99 — DDDs
    brasileiros reais começam em 11) + número de 8 (fixo) ou 9 (celular) dígitos.
    Normaliza para o formato E.164 (+55DDDNNNNNNNNN) — formato único e ordenável para
    armazenamento, nunca o texto livre digitado pelo usuário."""
    if telefone is None:
        return False, None, "Telefone é obrigatório."
    _digitos = re.sub(r"\D", "", str(telefone))
    # remove o código do país se já vier digitado (55...)
    if _digitos.startswith("55") and len(_digitos) in (12, 13):
        _digitos = _digitos[2:]
    if len(_digitos) not in (10, 11):
        return False, None, "Telefone inválido — informe DDD + número (10 ou 11 dígitos)."
    _ddd = _digitos[:2]
    if not (11 <= int(_ddd) <= 99):
        return False, None, "DDD inválido."
    _numero = _digitos[2:]
    if len(_numero) == 9 and _numero[0] != "9":
        return False, None, "Celular com 9 dígitos deve começar com 9."
    _normalizado = f"+55{_ddd}{_numero}"
    return True, _normalizado, ""


def formatar_telefone_exibicao(telefone_e164: str) -> str:
    """+5511987654321 -> (11) 98765-4321. Puramente cosmético; nunca usado para
    armazenamento/comparação (isso é sempre feito no formato E.164 normalizado)."""
    try:
        _digitos = re.sub(r"\D", "", str(telefone_e164 or ""))
        if _digitos.startswith("55"):
            _digitos = _digitos[2:]
        if len(_digitos) == 11:
            return f"({_digitos[:2]}) {_digitos[2:7]}-{_digitos[7:]}"
        if len(_digitos) == 10:
            return f"({_digitos[:2]}) {_digitos[2:6]}-{_digitos[6:]}"
        return str(telefone_e164 or "")
    except Exception:
        return str(telefone_e164 or "")


# ==============================================================================
# CEP / Endereço
# ==============================================================================

def validar_cep(cep: str):
    """CEP brasileiro: 8 dígitos, normalizado para NNNNN-NNN."""
    if cep is None:
        return False, None, "CEP é obrigatório."
    _digitos = re.sub(r"\D", "", str(cep))
    if len(_digitos) != 8:
        return False, None, "CEP inválido (deve ter 8 dígitos)."
    return True, f"{_digitos[:5]}-{_digitos[5:]}", ""


_UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def validar_uf(uf: str):
    """UF: uma das 26 siglas oficiais + DF — nunca aceita uma sigla inventada."""
    if uf is None:
        return False, None, "UF é obrigatória."
    _u = str(uf).strip().upper()
    if _u not in _UFS_VALIDAS:
        return False, None, "UF inválida."
    return True, _u, ""


def validar_endereco(logradouro, numero, bairro, cidade, uf, cep, complemento=""):
    """Valida o endereço completo (usado no cadastro/perfil). Campos obrigatórios:
    logradouro, número, bairro, cidade, UF, CEP — complemento é opcional. Retorna
    (ok, dict_normalizado_ou_None, lista_de_erros)."""
    _erros = []
    _log = " ".join(str(logradouro or "").split())
    if len(_log) < 3:
        _erros.append("Logradouro é obrigatório.")
    _num = str(numero or "").strip()
    if not _num:
        _erros.append("Número é obrigatório (use 'S/N' quando não houver numeração).")
    _bai = " ".join(str(bairro or "").split())
    if len(_bai) < 2:
        _erros.append("Bairro é obrigatório.")
    _cid = " ".join(str(cidade or "").split())
    if len(_cid) < 2:
        _erros.append("Cidade é obrigatória.")
    _ok_uf, _uf_norm, _erro_uf = validar_uf(uf)
    if not _ok_uf:
        _erros.append(_erro_uf)
    _ok_cep, _cep_norm, _erro_cep = validar_cep(cep)
    if not _ok_cep:
        _erros.append(_erro_cep)
    if _erros:
        return False, None, _erros
    return True, {
        "logradouro": _log, "numero": _num, "complemento": str(complemento or "").strip(),
        "bairro": _bai, "cidade": _cid, "uf": _uf_norm, "cep": _cep_norm,
    }, []


# ==============================================================================
# Senha
# ==============================================================================

_SENHA_MIN_LEN = 8
# Lista curta e real de senhas triviais — nunca pretende ser exaustiva (isso é papel de
# um serviço dedicado tipo "Have I Been Pwned"), só barra os casos mais óbvios que um
# usuário apressado tentaria digitar num formulário de cadastro.
_SENHAS_TRIVIAIS = {
    "12345678", "123456789", "password", "senha123", "qwerty123", "11111111",
    "00000000", "abc12345", "12345678900", "iloveyou", "admin123", "senhasenha",
    # Comuns que PASSAM na regra das 3 classes (é aqui que a lista realmente ajuda —
    # as puramente numéricas/minúsculas já caem na checagem de classes abaixo):
    "senha@123", "senha123!", "p@ssw0rd", "password1!", "qwerty@123", "admin@123",
    "master@123", "brasil@123", "brasil@2024", "mudar@123", "trocar@123", "senha@2024",
}


def validar_forca_senha(senha: str, email: str = "", nome: str = ""):
    """Política de senha: >=8 caracteres, pelo menos 3 das 4 classes (maiúscula,
    minúscula, dígito, símbolo), rejeita a lista de senhas triviais e — quando
    `email`/`nome` são informados — rejeita senhas que CONTENHAM o e-mail ou o nome
    do próprio usuário (vetor comum de senha fraca). Retorna (ok, motivo, nivel) —
    nivel in {'fraca','media','forte'} para feedback visual mesmo quando ok=True
    (senha aceitável mas não necessariamente forte).

    `email`/`nome` são OPCIONAIS e retrocompatíveis: chamadas antigas
    (`validar_forca_senha(senha)`) seguem funcionando exatamente igual."""
    if senha is None:
        return False, "Senha é obrigatória.", "fraca"
    _s = str(senha)
    if len(_s) < _SENHA_MIN_LEN:
        return False, f"Senha muito curta (mínimo {_SENHA_MIN_LEN} caracteres).", "fraca"
    if len(_s) > 128:
        return False, "Senha excede o tamanho máximo permitido (128 caracteres).", "fraca"
    if _s.lower() in _SENHAS_TRIVIAIS:
        return False, "Senha muito comum/óbvia — escolha outra.", "fraca"
    # [HARDENING] Não deixe a senha conter o próprio e-mail ou nome (ex.: senha = "Joao@2024"
    # para o usuário João, ou o começo do e-mail). Só considera pedaços com >=4 caracteres,
    # para não gerar falso-positivo com nomes/logins muito curtos.
    _sl = _s.lower()
    _local = str(email or "").split("@")[0].strip().lower()
    if len(_local) >= 4 and _local in _sl:
        return False, "A senha não pode conter o seu e-mail — escolha outra.", "fraca"
    for _tok in str(nome or "").split():
        if len(_tok) >= 4 and _tok.lower() in _sl:
            return False, "A senha não pode conter o seu nome — escolha outra.", "fraca"
    _tem_maiuscula = any(c.isupper() for c in _s)
    _tem_minuscula = any(c.islower() for c in _s)
    _tem_digito = any(c.isdigit() for c in _s)
    _tem_simbolo = any(not c.isalnum() for c in _s)
    _classes = sum([_tem_maiuscula, _tem_minuscula, _tem_digito, _tem_simbolo])
    if _classes < 3:
        return False, ("Senha fraca — combine ao menos 3 destes: letra maiúscula, "
                       "letra minúscula, número e símbolo."), "fraca"
    _nivel = "forte" if (len(_s) >= 12 and _classes == 4) else "media"
    return True, "", _nivel


def senhas_conferem(senha: str, confirmacao: str):
    """Comparação em tempo constante-ish (não é criptográfico, é só para não dar dica de
    onde a diferença começa via short-circuit óbvio) — suficiente para um formulário,
    a segurança real está no hash, nunca na comparação de texto puro."""
    if senha is None or confirmacao is None:
        return False
    _a, _b = str(senha), str(confirmacao)
    if len(_a) != len(_b):
        return False
    _diff = 0
    for _ca, _cb in zip(_a, _b):
        _diff |= ord(_ca) ^ ord(_cb)
    return _diff == 0


# ==============================================================================
# Código de recuperação (OTP)
# ==============================================================================

_OTP_RE = re.compile(r"^\d{6}$")


def validar_formato_otp(codigo: str):
    """Formato do código de recuperação: exatamente 6 dígitos. NÃO valida se o código é
    o correto (isso é responsabilidade do Supabase Auth, via verify_otp) — só garante que
    o que o usuário digitou tem o formato esperado antes de gastar uma tentativa de rede."""
    if codigo is None:
        return False, None, "Código é obrigatório."
    _c = re.sub(r"\D", "", str(codigo)).strip()
    if not _OTP_RE.match(_c):
        return False, None, "Código inválido — deve ter exatamente 6 dígitos."
    return True, _c, ""
