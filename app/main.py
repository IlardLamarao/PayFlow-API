"""Ponto de entrada da PayFlow API.

Sobe o app FastAPI com Swagger em /docs, o tratamento global de erros e os
4 endpoints da ficha do Domínio 7. As rotas só recebem e devolvem DTOs de
`schemas.py` e delegam toda regra de negócio para `services.py`.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import services
from app.database import get_db, init_db
from app.exceptions import ErroDeDominio
from app.schemas import (
    CancelamentoDTO,
    CriarFaturaDTO,
    ErroPadronizadoDTO,
    ExtratoClienteDTO,
    FaturaDTO,
    PagarFaturaDTO,
)

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
    openapi_tags=[
        {"name": "Faturas", "description": "Emissão, pagamento e cancelamento de faturas de cobrança."},
        {"name": "Clientes", "description": "Consulta do extrato de faturas por CPF/CNPJ."},
    ],
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


# ----------------------------------------------------------------------------
# Endpoints (Domínio 7 — PayFlow API)
# ----------------------------------------------------------------------------
def _erro(descricao: str, codigo: str, mensagem: str) -> dict:
    """Documenta no Swagger uma resposta de erro com o JSON padronizado."""
    return {
        "model": ErroPadronizadoDTO,
        "description": descricao,
        "content": {"application/json": {"example": {
            "codigo_erro": codigo, "mensagem": mensagem, "timestamp": "2026-11-19T14:30:00Z",
        }}},
    }


_ID_FATURA = Path(..., description="Identificador da fatura.", examples=["FAT-2026-001"])


@app.post(
    "/api/v1/faturas",
    response_model=FaturaDTO,
    status_code=201,
    tags=["Faturas"],
    summary="Gerar nova fatura de cobrança",
    responses={
        400: _erro(
            "valor_reais <= 0, vencimento no passado, CPF/CNPJ inválido ou campo ausente.",
            "VENCIMENTO_NO_PASSADO", "A data de vencimento 2026-01-10 está no passado.",
        ),
    },
)
def gerar_fatura(payload: CriarFaturaDTO, db: Session = Depends(get_db)) -> FaturaDTO:
    """Cria uma fatura com status **PENDENTE** e devolve o Pix copia-e-cola (BR Code) gerado.

    - `valor_reais` deve ser maior que zero.
    - `data_vencimento` não pode estar no passado (hoje é aceito).
    - `cliente_cnpj_cpf` aceita CPF ou CNPJ, com ou sem máscara.
    """
    return services.criar_fatura(db, payload)


@app.get(
    "/api/v1/clientes/{cnpj_cpf}/extrato",
    response_model=ExtratoClienteDTO,
    status_code=200,
    tags=["Clientes"],
    summary="Consultar extrato do cliente",
    responses={
        400: _erro("CPF/CNPJ informado é inválido.", "DOCUMENTO_INVALIDO", "CPF inválido."),
        404: _erro(
            "O cliente não possui faturas no sistema.",
            "CLIENTE_SEM_FATURAS", "O cliente 52998224725 não possui faturas no sistema.",
        ),
    },
)
def consultar_extrato(
    cnpj_cpf: str = Path(..., description="CPF ou CNPJ do cliente, com ou sem máscara.",
                         examples=["52998224725"]),
    db: Session = Depends(get_db),
) -> ExtratoClienteDTO:
    """Lista todas as faturas do cliente com os totais **pendente** e **pago**.

    Faturas CANCELADAS aparecem na lista, mas não entram nos totais.
    """
    return services.consultar_extrato(db, cnpj_cpf)


@app.put(
    "/api/v1/faturas/{id_fatura}/pagar",
    response_model=FaturaDTO,
    status_code=200,
    tags=["Faturas"],
    summary="Registrar pagamento/liquidação",
    responses={
        400: _erro(
            "A fatura já está PAGA ou CANCELADA, ou o corpo é inválido.",
            "FATURA_JA_PAGA", "A fatura FAT-2026-001 já está PAGA.",
        ),
        404: _erro("Fatura inexistente.", "FATURA_NAO_ENCONTRADA", "Fatura FAT-2026-999 não encontrada."),
    },
)
def pagar_fatura(
    id_fatura: str = _ID_FATURA,
    payload: PagarFaturaDTO = Body(...),
    db: Session = Depends(get_db),
) -> FaturaDTO:
    """Liquida uma fatura **PENDENTE**: muda o status para PAGA e grava `data_pagamento`.

    `forma_pagamento` aceita somente `PIX` ou `BOLETO`.
    """
    return services.pagar_fatura(db, id_fatura, payload)


@app.delete(
    "/api/v1/faturas/{id_fatura}",
    response_model=CancelamentoDTO,
    status_code=200,
    tags=["Faturas"],
    summary="Cancelar fatura",
    responses={
        400: _erro(
            "A fatura já foi PAGA ou já está CANCELADA.",
            "FATURA_JA_PAGA", "A fatura FAT-2026-001 já foi PAGA e não pode ser cancelada.",
        ),
        404: _erro("Fatura inexistente.", "FATURA_NAO_ENCONTRADA", "Fatura FAT-2026-999 não encontrada."),
    },
)
def cancelar_fatura(id_fatura: str = _ID_FATURA, db: Session = Depends(get_db)) -> CancelamentoDTO:
    """Cancela a fatura (exclusão lógica): o registro continua no extrato com status CANCELADA."""
    return services.cancelar_fatura(db, id_fatura)
