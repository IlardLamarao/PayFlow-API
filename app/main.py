"""Ponto de entrada da PayFlow API.

Nesta etapa (Parte 1) o app sobe com Swagger em /docs e com o tratamento
global de erros. Os 4 endpoints são adicionados na Parte 2.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import init_db
from app.exceptions import ErroDeDominio
from app.schemas import ErroPadronizadoDTO

logger = logging.getLogger("payflow")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="PayFlow API",
    description=(
        "API RESTful de faturamento e cobranças Pix/Boleto da fintech PayFlow Gestão.\n\n"
        "Todos os erros 4xx seguem o formato `{codigo_erro, mensagem, timestamp}`."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


def _resposta_erro(status: int, codigo_erro: str, mensagem: str, headers: dict | None = None) -> JSONResponse:
    corpo = ErroPadronizadoDTO.novo(codigo_erro, mensagem)
    return JSONResponse(status_code=status, content=corpo.model_dump(), headers=headers)


def _mensagem_validacao(exc: RequestValidationError) -> str:
    partes = []
    for erro in exc.errors():
        local = [str(p) for p in erro.get("loc", ()) if p not in ("body", "query", "path")]
        campo = ".".join(local) or "requisição"
        motivo = str(erro.get("msg", "valor inválido")).removeprefix("Value error, ")
        partes.append(f"{campo}: {motivo}")
    return "Requisição inválida. " + "; ".join(partes)


@app.exception_handler(ErroDeDominio)
async def tratar_erro_de_dominio(_request: Request, exc: ErroDeDominio) -> JSONResponse:
    return _resposta_erro(exc.status_code, exc.codigo_erro, exc.mensagem)


@app.exception_handler(RequestValidationError)
async def tratar_validacao(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # A ficha exige 400 Bad Request (o padrão do FastAPI seria 422).
    return _resposta_erro(400, "REQUISICAO_INVALIDA", _mensagem_validacao(exc))


@app.exception_handler(StarletteHTTPException)
async def tratar_http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codigos = {404: "RECURSO_NAO_ENCONTRADO", 405: "METODO_NAO_PERMITIDO"}
    mensagens = {
        404: "Recurso não encontrado.",
        405: "Método HTTP não permitido para este recurso.",
    }
    return _resposta_erro(
        exc.status_code,
        codigos.get(exc.status_code, "ERRO_HTTP"),
        mensagens.get(exc.status_code, str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def tratar_erro_inesperado(_request: Request, exc: Exception) -> JSONResponse:
    # O detalhe vai para o log do servidor; o cliente nunca vê stack trace.
    logger.exception("Erro inesperado", exc_info=exc)
    return _resposta_erro(500, "ERRO_INTERNO", "Erro interno inesperado. Tente novamente mais tarde.")
