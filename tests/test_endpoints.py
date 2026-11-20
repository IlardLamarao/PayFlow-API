"""Testes de sucesso e erro dos 4 endpoints da PayFlow API.

Cada teste roda num banco SQLite em memória novo, injetado pela sobrescrita
da dependência `get_db`, sem tocar no arquivo `payflow.db`.
"""

import re
from datetime import timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.pix import crc16_ccitt  # noqa: E402
from app.services import hoje_em_belem  # noqa: E402

CPF = "52998224725"
CPF_MASCARA = "529.982.247-25"
CAMPOS_ERRO = {"codigo_erro", "mensagem", "timestamp"}
CAMPOS_FATURA = {
    "id_fatura", "cliente_nome", "valor_reais", "data_vencimento",
    "linha_digitavel_pix", "status", "data_emissao", "data_pagamento",
}


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _db_de_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db_de_teste
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def _payload(**alteracoes):
    base = {
        "cliente_cnpj_cpf": CPF_MASCARA,
        "cliente_nome": "Maria das Dores Souza",
        "valor_reais": 450.00,
        "data_vencimento": (hoje_em_belem() + timedelta(days=30)).isoformat(),
        "descricao": "Mensalidade de novembro/2026",
    }
    base.update(alteracoes)
    return base


def _criar(client, **alteracoes) -> dict:
    r = client.post("/api/v1/faturas", json=_payload(**alteracoes))
    assert r.status_code == 201, r.text
    return r.json()


def _assert_erro(resposta, status: int, codigo: str):
    assert resposta.status_code == status, resposta.text
    corpo = resposta.json()
    assert set(corpo) == CAMPOS_ERRO
    assert corpo["codigo_erro"] == codigo


# ----------------------------------------------------------------------------
# POST /api/v1/faturas
# ----------------------------------------------------------------------------
def test_criar_fatura_retorna_201_com_pix(client):
    fatura = _criar(client)

    assert set(fatura) == CAMPOS_FATURA  # sem campos internos do banco
    assert re.fullmatch(r"FAT-\d{4}-\d{3,}", fatura["id_fatura"])
    assert fatura["status"] == "PENDENTE"
    assert fatura["valor_reais"] == 450.0
    assert fatura["data_pagamento"] is None
    pix = fatura["linha_digitavel_pix"]
    assert pix.startswith("000201") and "br.gov.bcb.pix" in pix and "5406450.00" in pix
    assert pix[-4:] == crc16_ccitt(pix[:-4])


def test_criar_fatura_gera_ids_sequenciais(client):
    primeiro = _criar(client)["id_fatura"]
    segundo = _criar(client)["id_fatura"]
    assert primeiro != segundo
    assert int(segundo.rsplit("-", 1)[1]) == int(primeiro.rsplit("-", 1)[1]) + 1


@pytest.mark.parametrize("valor", [0, -10.5])
def test_criar_fatura_valor_nao_positivo_retorna_400(client, valor):
    r = client.post("/api/v1/faturas", json=_payload(valor_reais=valor))
    _assert_erro(r, 400, "REQUISICAO_INVALIDA")
    assert "valor_reais" in r.json()["mensagem"]


def test_criar_fatura_vencimento_no_passado_retorna_400(client):
    ontem = (hoje_em_belem() - timedelta(days=1)).isoformat()
    r = client.post("/api/v1/faturas", json=_payload(data_vencimento=ontem))
    _assert_erro(r, 400, "VENCIMENTO_NO_PASSADO")


def test_criar_fatura_documento_invalido_retorna_400(client):
    r = client.post("/api/v1/faturas", json=_payload(cliente_cnpj_cpf="123.456.789-00"))
    _assert_erro(r, 400, "REQUISICAO_INVALIDA")


def test_criar_fatura_campo_obrigatorio_ausente_retorna_400(client):
    payload = _payload()
    del payload["descricao"]
    r = client.post("/api/v1/faturas", json=payload)
    _assert_erro(r, 400, "REQUISICAO_INVALIDA")
    assert "descricao" in r.json()["mensagem"]


# ----------------------------------------------------------------------------
# GET /api/v1/clientes/{cnpj_cpf}/extrato
# ----------------------------------------------------------------------------
def test_extrato_soma_pendente_e_pago(client):
    a = _criar(client, valor_reais=450.00)
    b = _criar(client, valor_reais=1200.00)
    client.put(f"/api/v1/faturas/{b['id_fatura']}/pagar",
               json={"forma_pagamento": "PIX", "codigo_comprovante": "TRX-998123"})

    r = client.get(f"/api/v1/clientes/{CPF}/extrato")
    assert r.status_code == 200
    extrato = r.json()
    assert extrato["cliente_cnpj_cpf"] == CPF
    assert extrato["cliente_nome"] == "Maria das Dores Souza"
    assert extrato["total_pendente_reais"] == 450.00
    assert extrato["total_pago_reais"] == 1200.00
    assert [f["id_fatura"] for f in extrato["faturas"]] == [a["id_fatura"], b["id_fatura"]]


def test_extrato_cliente_sem_faturas_retorna_404(client):
    r = client.get("/api/v1/clientes/11144477735/extrato")
    _assert_erro(r, 404, "CLIENTE_SEM_FATURAS")


def test_extrato_documento_invalido_retorna_400(client):
    r = client.get("/api/v1/clientes/123/extrato")
    _assert_erro(r, 400, "DOCUMENTO_INVALIDO")


# ----------------------------------------------------------------------------
# PUT /api/v1/faturas/{id_fatura}/pagar
# ----------------------------------------------------------------------------
def test_pagar_fatura_retorna_200_com_data_pagamento(client):
    fatura = _criar(client)
    r = client.put(f"/api/v1/faturas/{fatura['id_fatura']}/pagar",
                   json={"forma_pagamento": "PIX", "codigo_comprovante": "TRX-998123"})
    assert r.status_code == 200
    paga = r.json()
    assert set(paga) == CAMPOS_FATURA
    assert paga["status"] == "PAGA"
    assert paga["data_pagamento"] is not None


def test_pagar_fatura_inexistente_retorna_404(client):
    r = client.put("/api/v1/faturas/FAT-2026-999/pagar",
                   json={"forma_pagamento": "PIX", "codigo_comprovante": "TRX-1"})
    _assert_erro(r, 404, "FATURA_NAO_ENCONTRADA")


def test_pagar_fatura_ja_paga_retorna_400(client):
    fatura = _criar(client)
    url = f"/api/v1/faturas/{fatura['id_fatura']}/pagar"
    corpo = {"forma_pagamento": "BOLETO", "codigo_comprovante": "TRX-1"}
    assert client.put(url, json=corpo).status_code == 200
    _assert_erro(client.put(url, json=corpo), 400, "FATURA_JA_PAGA")


def test_pagar_fatura_cancelada_retorna_400(client):
    fatura = _criar(client)
    client.delete(f"/api/v1/faturas/{fatura['id_fatura']}")
    r = client.put(f"/api/v1/faturas/{fatura['id_fatura']}/pagar",
                   json={"forma_pagamento": "PIX", "codigo_comprovante": "TRX-1"})
    _assert_erro(r, 400, "FATURA_CANCELADA")


def test_pagar_com_forma_de_pagamento_invalida_retorna_400(client):
    fatura = _criar(client)
    r = client.put(f"/api/v1/faturas/{fatura['id_fatura']}/pagar",
                   json={"forma_pagamento": "CARTAO", "codigo_comprovante": "TRX-1"})
    _assert_erro(r, 400, "REQUISICAO_INVALIDA")
    assert "forma_pagamento" in r.json()["mensagem"]


# ----------------------------------------------------------------------------
# DELETE /api/v1/faturas/{id_fatura}
# ----------------------------------------------------------------------------
def test_cancelar_fatura_retorna_200(client):
    fatura = _criar(client)
    r = client.delete(f"/api/v1/faturas/{fatura['id_fatura']}")
    assert r.status_code == 200
    assert r.json() == {
        "mensagem": "Fatura cancelada com sucesso.",
        "id_fatura": fatura["id_fatura"],
        "status": "CANCELADA",
    }


def test_cancelar_fatura_inexistente_retorna_404(client):
    _assert_erro(client.delete("/api/v1/faturas/FAT-2026-999"), 404, "FATURA_NAO_ENCONTRADA")


def test_cancelar_fatura_paga_retorna_400(client):
    fatura = _criar(client)
    client.put(f"/api/v1/faturas/{fatura['id_fatura']}/pagar",
               json={"forma_pagamento": "PIX", "codigo_comprovante": "TRX-1"})
    _assert_erro(client.delete(f"/api/v1/faturas/{fatura['id_fatura']}"), 400, "FATURA_JA_PAGA")


def test_cancelar_fatura_ja_cancelada_retorna_400(client):
    fatura = _criar(client)
    url = f"/api/v1/faturas/{fatura['id_fatura']}"
    assert client.delete(url).status_code == 200
    _assert_erro(client.delete(url), 400, "FATURA_JA_CANCELADA")


# ----------------------------------------------------------------------------
# Swagger
# ----------------------------------------------------------------------------
def test_swagger_documenta_os_4_endpoints(client):
    caminhos = client.get("/openapi.json").json()["paths"]
    assert "post" in caminhos["/api/v1/faturas"]
    assert "get" in caminhos["/api/v1/clientes/{cnpj_cpf}/extrato"]
    assert "put" in caminhos["/api/v1/faturas/{id_fatura}/pagar"]
    assert "delete" in caminhos["/api/v1/faturas/{id_fatura}"]
