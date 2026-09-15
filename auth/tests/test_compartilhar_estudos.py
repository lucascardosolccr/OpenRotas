# -*- coding: utf-8 -*-
"""Testes do COMPARTILHAMENTO DE ESTUDOS entre perfis (auth_service). O acesso real é RLS no Supabase
(não testável aqui), então validamos: os GUARDA-CORPOS determinísticos (e-mail inválido, sem posse, id
ausente) e a FORMA das consultas (revogar filtra por owner_id; carregar_por_id NÃO filtra por user_id,
deixando a RLS decidir) via um cliente-fake que registra as chamadas.

Roda: `python3 -m pytest auth/tests/test_compartilhar_estudos.py`."""
from auth import auth_service


class _FakeQuery:
    def __init__(self, rec, tabela, data=None):
        self._rec, self._tabela, self._data = rec, tabela, data or []

    def select(self, *a, **k):
        return self

    def insert(self, payload):
        self._rec.setdefault("inserts", []).append((self._tabela, payload))
        return self

    def update(self, payload):
        self._rec.setdefault("updates", []).append((self._tabela, payload))
        return self

    def delete(self):
        self._rec.setdefault("deletes", []).append(self._tabela)
        return self

    def eq(self, col, val):
        self._rec.setdefault("eq", []).append((self._tabela, col, val))
        return self

    def gt(self, col, val):
        self._rec.setdefault("gt", []).append((self._tabela, col, val))
        return self

    def in_(self, col, vals):
        self._rec.setdefault("in", []).append((self._tabela, col, list(vals)))
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        class _R:
            pass
        _r = _R()
        _r.data = self._data
        return _r


class _FakeClient:
    def __init__(self, rec, dados_por_tabela=None):
        self._rec, self._dados = rec, dados_por_tabela or {}

    def table(self, nome):
        return _FakeQuery(self._rec, nome, self._dados.get(nome, []))


def _mock(monkeypatch, dados=None, rec=None):
    rec = rec if rec is not None else {}
    monkeypatch.setattr(auth_service, "_cliente_do_usuario",
                        lambda at="", rt="": _FakeClient(rec, dados))
    return rec


# ---- guarda-corpos determinísticos (não tocam no banco) ----------------------
def test_compartilhar_email_invalido_falha_sem_cliente(monkeypatch):
    # se chegar a chamar o cliente, o teste falha (não deve, e-mail é validado antes)
    monkeypatch.setattr(auth_service, "_cliente_do_usuario",
                        lambda at="", rt="": (_ for _ in ()).throw(AssertionError("não deveria chamar o cliente")))
    r = auth_service.compartilhar_estudo("u1", "e1", "email-invalido")
    assert not r.ok and "inv" in r.mensagem.lower()


def test_compartilhar_sem_estudo_id_falha(monkeypatch):
    _mock(monkeypatch)
    r = auth_service.compartilhar_estudo("u1", "", "colega@x.com")
    assert not r.ok


def test_carregar_por_id_sem_id_retorna_none(monkeypatch):
    _mock(monkeypatch)
    assert auth_service.carregar_estudo_por_id("") is None


def test_listar_recebidos_email_invalido_vazio(monkeypatch):
    _mock(monkeypatch)
    assert auth_service.listar_estudos_recebidos("nao-eh-email") == []


# ---- forma das consultas (com cliente-fake) ----------------------------------
def test_compartilhar_sem_posse_do_estudo_falha(monkeypatch):
    # estudos_salvos retorna vazio → não é dono → recusa, sem inserir
    rec = _mock(monkeypatch, dados={"estudos_salvos": []})
    r = auth_service.compartilhar_estudo("u1", "e1", "Colega@X.com")
    assert not r.ok
    assert "inserts" not in rec  # nunca inseriu compartilhamento


def test_compartilhar_sucesso_normaliza_email_e_insere(monkeypatch):
    rec = _mock(monkeypatch, dados={"estudos_salvos": [{"id": "e1", "nome": "ENEM"}]})
    r = auth_service.compartilhar_estudo("u1", "e1", "  Colega@X.com ", "oi")
    assert r.ok
    _tab, _payload = rec["inserts"][0]
    assert _tab == "estudos_compartilhados"
    assert _payload["destinatario_email"] == "colega@x.com"   # normalizado
    assert _payload["owner_id"] == "u1" and _payload["estudo_id"] == "e1"


def test_revogar_filtra_por_owner(monkeypatch):
    rec = _mock(monkeypatch)
    r = auth_service.revogar_compartilhamento("u1", "s1")
    assert r.ok
    assert ("estudos_compartilhados", "owner_id", "u1") in rec.get("eq", [])


def test_carregar_por_id_nao_filtra_por_user(monkeypatch):
    rec = _mock(monkeypatch, dados={"estudos_salvos": [{"id": "e9", "dados": [{"a": 1}]}]})
    out = auth_service.carregar_estudo_por_id("e9")
    assert out and out.get("id") == "e9"
    # só pode filtrar por id — NUNCA por user_id (senão o destinatário não leria)
    _eqs = rec.get("eq", [])
    assert ("estudos_salvos", "id", "e9") in _eqs
    assert not any(col == "user_id" for _t, col, _v in _eqs)


# ---- notificação: badge + e-mail ---------------------------------------------
def test_compartilhar_com_o_proprio_email_e_recusado(monkeypatch):
    # se o destinatário é o próprio remetente, recusa ANTES de tocar no banco
    monkeypatch.setattr(auth_service, "_cliente_do_usuario",
                        lambda at="", rt="": (_ for _ in ()).throw(AssertionError("não deveria chamar o cliente")))
    r = auth_service.compartilhar_estudo("u1", "e1", "eu@x.com", remetente_email="Eu@X.com")
    assert not r.ok


def test_compartilhar_dispara_email_best_effort(monkeypatch):
    rec = _mock(monkeypatch, dados={"estudos_salvos": [{"id": "e1", "nome": "ENEM 2026"}]})
    _enviados = {}

    def _fake_envia(dest, nome, mail, estudo, msg=""):
        _enviados.update({"dest": dest, "estudo": estudo, "remetente": nome})
        return True
    import auth.email_service as _es
    monkeypatch.setattr(_es, "enviar_notificacao_compartilhamento", _fake_envia)
    r = auth_service.compartilhar_estudo("u1", "e1", "colega@x.com", "olha isso",
                                         remetente_nome="Ana", remetente_email="ana@x.com")
    assert r.ok
    assert _enviados.get("dest") == "colega@x.com"
    assert _enviados.get("estudo") == "ENEM 2026"


def test_email_falho_nao_derruba_compartilhamento(monkeypatch):
    _mock(monkeypatch, dados={"estudos_salvos": [{"id": "e1", "nome": "X"}]})
    import auth.email_service as _es
    monkeypatch.setattr(_es, "enviar_notificacao_compartilhamento",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp caiu")))
    r = auth_service.compartilhar_estudo("u1", "e1", "colega@x.com", remetente_email="ana@x.com")
    assert r.ok  # o compartilhamento já foi persistido; e-mail é cortesia


def test_contar_recebidos_novos_email_invalido_zero(monkeypatch):
    _mock(monkeypatch)
    assert auth_service.contar_estudos_recebidos_novos("u1", "nao-eh-email") == 0


def test_contar_recebidos_novos_conta_lista(monkeypatch):
    rec = _mock(monkeypatch, dados={
        "profiles": [{"estudos_recebidos_vistos_em": None}],
        "estudos_compartilhados": [{"id": "s1", "created_at": "2024-01-02"},
                                   {"id": "s2", "created_at": "2024-01-03"}]})
    n = auth_service.contar_estudos_recebidos_novos("u1", "eu@x.com")
    assert n == 2
    # filtra pelo e-mail normalizado do destinatário
    assert ("estudos_compartilhados", "destinatario_email", "eu@x.com") in rec.get("eq", [])


def test_marcar_vistos_atualiza_profile(monkeypatch):
    rec = _mock(monkeypatch)
    assert auth_service.marcar_recebidos_como_vistos("u1") is True
    # faz um UPDATE em profiles com a data de visualização, filtrando pelo próprio id
    _tabs_upd = [t for t, _p in rec.get("updates", [])]
    assert "profiles" in _tabs_upd
    _payload = dict(rec["updates"][0][1])
    assert "estudos_recebidos_vistos_em" in _payload
    assert ("profiles", "id", "u1") in rec.get("eq", [])
