"""Testes do tratamento global de erros (exigem fastapi, sqlalchemy e httpx)."""

import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.exceptions import ConflitoError, RecursoNaoEncontradoError, RequisicaoInvalidaError  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import CriarFaturaDTO  # noqa: E402

CAMPOS_ERRO = {"codigo_erro", "mensagem", "timestamp"}


# Rotas temporárias, só para provocar cada tipo de erro.
@app.get("/_teste/400")
def _rota_400():
    raise RequisicaoInvalidaError("Fatura já paga.")


@app.get("/_teste/404")
def _rota_404():
    raise RecursoNaoEncontradoError("Fatura FAT-2026-999 não encontrada.")


@app.get("/_teste/409")
def _rota_409():
    raise ConflitoError("Conflito de estado.")


@app.get("/_teste/500")
def _rota_500():
    raise RuntimeError("segredo-interno-do-servidor")


@app.post("/_teste/validacao")
def _rota_validacao(payload: CriarFaturaDTO):
    return {"ok": True}


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.mark.parametrize("rota,status,codigo", [
    ("/_teste/400", 400, "REQUISICAO_INVALIDA"),
    ("/_teste/404", 404, "RECURSO_NAO_ENCONTRADO"),
    ("/_teste/409", 409, "CONFLITO"),
])
def test_erros_de_dominio(client, rota, status, codigo):
    r = client.get(rota)
    assert r.status_code == status
    corpo = r.json()
    assert set(corpo) == CAMPOS_ERRO
    assert corpo["codigo_erro"] == codigo
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", corpo["timestamp"])


def test_validacao_retorna_400_e_nao_422(client):
    r = client.post("/_teste/validacao", json={"cliente_nome": "X", "valor_reais": -3})
    assert r.status_code == 400
    corpo = r.json()
    assert set(corpo) == CAMPOS_ERRO
    assert corpo["codigo_erro"] == "REQUISICAO_INVALIDA"
    assert "valor_reais" in corpo["mensagem"]


def test_cpf_invalido_retorna_400(client):
    r = client.post("/_teste/validacao", json={
        "cliente_cnpj_cpf": "111.111.111-11", "cliente_nome": "X", "valor_reais": 10,
        "data_vencimento": "2026-12-15", "descricao": "d",
    })
    assert r.status_code == 400
    assert "CPF" in r.json()["mensagem"]


def test_json_malformado_retorna_400(client):
    r = client.post("/_teste/validacao", content="{nao e json", headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert set(r.json()) == CAMPOS_ERRO


def test_rota_inexistente_e_metodo_errado(client):
    r404 = client.get("/rota/que/nao/existe")
    assert r404.status_code == 404 and set(r404.json()) == CAMPOS_ERRO
    r405 = client.post("/_teste/404")
    assert r405.status_code == 405 and set(r405.json()) == CAMPOS_ERRO


def test_erro_inesperado_nao_vaza_stack_trace(client):
    r = client.get("/_teste/500")
    assert r.status_code == 500
    corpo = r.json()
    assert set(corpo) == CAMPOS_ERRO
    assert corpo["codigo_erro"] == "ERRO_INTERNO"
    assert "segredo-interno" not in r.text
    assert "Traceback" not in r.text


def test_swagger_ativo(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
