"""Testes complementares de borda da PayFlow API (Parte 3).

Cobrem os casos-limite das decisões de especificação: CNPJ com máscara,
extrato com faturas canceladas, vencimento no dia de hoje, além de
normalizações e do contrato publicado no Swagger.
"""

from datetime import timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

from app.services import hoje_em_belem  # noqa: E402
from tests.test_endpoints import (  # noqa: E402,F401  (client é fixture)
    CPF,
    _assert_erro,
    _criar,
    _payload,
    client,
)

CNPJ = "11222333000181"
CNPJ_MASCARA = "11.222.333/0001-81"
PAGAMENTO_PIX = {"forma_pagamento": "PIX", "codigo_comprovante": "TRX-1"}


# ----------------------------------------------------------------------------
# CNPJ com máscara
# ----------------------------------------------------------------------------
def test_cnpj_com_mascara_e_aceito_e_normalizado(client):
    fatura = _criar(client, cliente_cnpj_cpf=CNPJ_MASCARA, cliente_nome="Comercial Ver-o-Peso LTDA")

    r = client.get(f"/api/v1/clientes/{CNPJ}/extrato")
    assert r.status_code == 200, r.text
    extrato = r.json()
    assert extrato["cliente_cnpj_cpf"] == CNPJ
    assert extrato["cliente_nome"] == "Comercial Ver-o-Peso LTDA"
    assert [f["id_fatura"] for f in extrato["faturas"]] == [fatura["id_fatura"]]


def test_cnpj_sem_mascara_e_com_mascara_sao_o_mesmo_cliente(client):
    _criar(client, cliente_cnpj_cpf=CNPJ_MASCARA, valor_reais=100.00)
    _criar(client, cliente_cnpj_cpf=CNPJ, valor_reais=50.00)

    extrato = client.get(f"/api/v1/clientes/{CNPJ}/extrato").json()
    assert len(extrato["faturas"]) == 2
    assert extrato["total_pendente_reais"] == 150.00


def test_cnpj_com_digito_verificador_errado_retorna_400(client):
    r = client.post("/api/v1/faturas", json=_payload(cliente_cnpj_cpf="11.222.333/0001-82"))
    _assert_erro(r, 400, "REQUISICAO_INVALIDA")
    assert "cliente_cnpj_cpf" in r.json()["mensagem"]


def test_extrato_aceita_cpf_mascarado_na_url(client):
    _criar(client)
    r = client.get("/api/v1/clientes/529.982.247-25/extrato")
    assert r.status_code == 200, r.text
    assert r.json()["cliente_cnpj_cpf"] == CPF


def test_extrato_de_um_cliente_nao_mistura_faturas_de_outro(client):
    _criar(client)  # CPF
    _criar(client, cliente_cnpj_cpf=CNPJ_MASCARA)

    extrato = client.get(f"/api/v1/clientes/{CPF}/extrato").json()
    assert len(extrato["faturas"]) == 1


# ----------------------------------------------------------------------------
# Extrato com faturas canceladas
# ----------------------------------------------------------------------------
def test_extrato_lista_canceladas_mas_fora_dos_totais(client):
    pendente = _criar(client, valor_reais=100.00)
    paga = _criar(client, valor_reais=200.00)
    cancelada = _criar(client, valor_reais=300.00)
    client.put(f"/api/v1/faturas/{paga['id_fatura']}/pagar", json=PAGAMENTO_PIX)
    client.delete(f"/api/v1/faturas/{cancelada['id_fatura']}")

    extrato = client.get(f"/api/v1/clientes/{CPF}/extrato").json()
    status = {f["id_fatura"]: f["status"] for f in extrato["faturas"]}
    assert status == {
        pendente["id_fatura"]: "PENDENTE",
        paga["id_fatura"]: "PAGA",
        cancelada["id_fatura"]: "CANCELADA",
    }
    assert extrato["total_pendente_reais"] == 100.00
    assert extrato["total_pago_reais"] == 200.00


def test_extrato_so_com_canceladas_retorna_200_com_totais_zerados(client):
    fatura = _criar(client)
    client.delete(f"/api/v1/faturas/{fatura['id_fatura']}")

    r = client.get(f"/api/v1/clientes/{CPF}/extrato")
    assert r.status_code == 200  # o cliente tem faturas, mesmo que canceladas
    extrato = r.json()
    assert extrato["total_pendente_reais"] == 0
    assert extrato["total_pago_reais"] == 0
    assert extrato["faturas"][0]["status"] == "CANCELADA"


def test_totais_do_extrato_tem_duas_casas(client):
    _criar(client, valor_reais=0.1)
    _criar(client, valor_reais=0.2)
    extrato = client.get(f"/api/v1/clientes/{CPF}/extrato").json()
    assert extrato["total_pendente_reais"] == 0.3


# ----------------------------------------------------------------------------
# Vencimento
# ----------------------------------------------------------------------------
def test_fatura_com_vencimento_hoje_e_aceita(client):
    hoje = hoje_em_belem().isoformat()
    fatura = _criar(client, data_vencimento=hoje)
    assert fatura["data_vencimento"] == hoje
    assert fatura["status"] == "PENDENTE"


def test_fatura_vencendo_hoje_pode_ser_paga(client):
    fatura = _criar(client, data_vencimento=hoje_em_belem().isoformat())
    r = client.put(f"/api/v1/faturas/{fatura['id_fatura']}/pagar", json=PAGAMENTO_PIX)
    assert r.status_code == 200
    assert r.json()["status"] == "PAGA"


def test_vencimento_em_formato_invalido_retorna_400(client):
    r = client.post("/api/v1/faturas", json=_payload(data_vencimento="15/12/2026"))
    _assert_erro(r, 400, "REQUISICAO_INVALIDA")
    assert "data_vencimento" in r.json()["mensagem"]


def test_vencimento_muito_antigo_retorna_400(client):
    antigo = (hoje_em_belem() - timedelta(days=365)).isoformat()
    _assert_erro(client.post("/api/v1/faturas", json=_payload(data_vencimento=antigo)),
                 400, "VENCIMENTO_NO_PASSADO")


# ----------------------------------------------------------------------------
# Outras bordas
# ----------------------------------------------------------------------------
def test_valor_menor_que_um_centavo_retorna_400(client):
    r = client.post("/api/v1/faturas", json=_payload(valor_reais=0.004))
    _assert_erro(r, 400, "REQUISICAO_INVALIDA")


def test_id_da_fatura_em_minusculas_e_encontrado(client):
    fatura = _criar(client)
    r = client.put(f"/api/v1/faturas/{fatura['id_fatura'].lower()}/pagar", json=PAGAMENTO_PIX)
    assert r.status_code == 200
    assert r.json()["id_fatura"] == fatura["id_fatura"]


# ----------------------------------------------------------------------------
# Contrato publicado no Swagger
# ----------------------------------------------------------------------------
def test_swagger_documenta_status_e_exemplos_de_cada_rota(client):
    caminhos = client.get("/openapi.json").json()["paths"]
    esperados = {
        ("/api/v1/faturas", "post"): {"201", "400"},
        ("/api/v1/clientes/{cnpj_cpf}/extrato", "get"): {"200", "400", "404"},
        ("/api/v1/faturas/{id_fatura}/pagar", "put"): {"200", "400", "404"},
        ("/api/v1/faturas/{id_fatura}", "delete"): {"200", "400", "404"},
    }
    for (rota, verbo), codigos in esperados.items():
        operacao = caminhos[rota][verbo]
        assert operacao["summary"] and operacao["description"] and operacao["tags"]
        assert codigos <= set(operacao["responses"]), (rota, verbo)
        assert "422" not in operacao["responses"], f"{verbo.upper()} {rota} ainda documenta 422"
        for codigo in codigos:
            conteudo = operacao["responses"][codigo]["content"]["application/json"]
            assert "example" in conteudo or "examples" in conteudo, (rota, verbo, codigo)


def test_swagger_tem_exemplos_de_request(client):
    caminhos = client.get("/openapi.json").json()["paths"]
    for rota, verbo in [("/api/v1/faturas", "post"), ("/api/v1/faturas/{id_fatura}/pagar", "put")]:
        corpo = caminhos[rota][verbo]["requestBody"]["content"]["application/json"]
        assert len(corpo["examples"]) >= 2
