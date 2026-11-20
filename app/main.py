"""Ponto de entrada da PayFlow API.

Sobe o app FastAPI com Swagger em /docs, o tratamento global de erros e os
4 endpoints da ficha do Domínio 7. As rotas só recebem e devolvem DTOs de
`schemas.py` e delegam toda regra de negócio para `services.py`.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
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
        "API RESTful de faturamento e cobranças Pix/Boleto da fintech **PayFlow Gestão** "
        "(Domínio 7 — Marco 1).\n\n"
        "**Fluxo da fatura:** `PENDENTE` → `PAGA` (via PUT /pagar) ou `PENDENTE` → `CANCELADA` "
        "(via DELETE). Fatura PAGA não pode ser cancelada.\n\n"
        "**Erros:** todas as respostas 4xx/5xx seguem o formato "
        "`{codigo_erro, mensagem, timestamp}`, sem stack trace. Erros de validação de entrada "
        "retornam **400** (e não 422)."
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
# Exemplos usados na documentação do Swagger
# ----------------------------------------------------------------------------
_TIMESTAMP_EXEMPLO = "2026-11-19T14:30:00Z"


def _erro(descricao: str, *exemplos: tuple[str, str, str]) -> dict:
    """Documenta no Swagger uma resposta de erro com o JSON padronizado.

    Cada exemplo é `(titulo, codigo_erro, mensagem)` e vira uma opção do
    seletor "Examples" da resposta.
    """
    return {
        "model": ErroPadronizadoDTO,
        "description": descricao,
        "content": {"application/json": {"examples": {
            codigo: {
                "summary": titulo,
                "value": {"codigo_erro": codigo, "mensagem": mensagem, "timestamp": _TIMESTAMP_EXEMPLO},
            }
            for titulo, codigo, mensagem in exemplos
        }}},
    }


def _sucesso(descricao: str, exemplo: dict) -> dict:
    """Documenta no Swagger uma resposta de sucesso com um exemplo completo."""
    return {"description": descricao, "content": {"application/json": {"example": exemplo}}}


# BR Code real gerado por `gerar_br_code` para a fatura de exemplo (CRC16 válido).
_PIX_EXEMPLO = (
    "00020101021226890014br.gov.bcb.pix01365f9c1f4e-8d3a-4b7e-9a21-0c6d2e7b4a11"
    "0227MENSALIDADE DE NOVEMBRO20265204000053039865406450.005802BR5914PAYFLOW GESTAO"
    "6005BELEM62140510FAT202600163044396"
)
_FATURA_PENDENTE = {
    "id_fatura": "FAT-2026-001",
    "cliente_nome": "Maria das Dores Souza",
    "valor_reais": 450.00,
    "data_vencimento": "2026-12-15",
    "linha_digitavel_pix": _PIX_EXEMPLO,
    "status": "PENDENTE",
    "data_emissao": "2026-11-19T17:30:00Z",
    "data_pagamento": None,
}
_FATURA_PAGA = {**_FATURA_PENDENTE, "status": "PAGA", "data_pagamento": "2026-11-20T13:05:42Z"}

_ERRO_404_FATURA = _erro(
    "Não existe fatura com o ID informado.",
    ("Fatura inexistente", "FATURA_NAO_ENCONTRADA", "Fatura FAT-2026-999 não encontrada."),
)

_EXEMPLOS_CRIAR = {
    "cpf_com_mascara": {
        "summary": "Pessoa física (CPF com máscara)",
        "value": {
            "cliente_cnpj_cpf": "529.982.247-25",
            "cliente_nome": "Maria das Dores Souza",
            "valor_reais": 450.00,
            "data_vencimento": "2026-12-15",
            "descricao": "Mensalidade de novembro/2026",
        },
    },
    "cnpj_com_mascara": {
        "summary": "Pessoa jurídica (CNPJ com máscara)",
        "value": {
            "cliente_cnpj_cpf": "11.222.333/0001-81",
            "cliente_nome": "Comercial Ver-o-Peso LTDA",
            "valor_reais": 1890.90,
            "data_vencimento": "2026-12-31",
            "descricao": "Licença anual do sistema PayFlow",
        },
    },
    "valor_invalido": {
        "summary": "Inválido: valor_reais <= 0 (retorna 400)",
        "value": {
            "cliente_cnpj_cpf": "52998224725",
            "cliente_nome": "Maria das Dores Souza",
            "valor_reais": 0,
            "data_vencimento": "2026-12-15",
            "descricao": "Valor zerado",
        },
    },
}

_EXEMPLOS_PAGAR = {
    "pix": {"summary": "Pagamento via PIX", "value": {"forma_pagamento": "PIX", "codigo_comprovante": "TRX998123"}},
    "boleto": {
        "summary": "Pagamento via BOLETO",
        "value": {"forma_pagamento": "BOLETO", "codigo_comprovante": "34191.79001 01043.510047"},
    },
    "forma_invalida": {
        "summary": "Inválido: forma diferente de PIX/BOLETO (retorna 400)",
        "value": {"forma_pagamento": "CARTAO", "codigo_comprovante": "TRX998123"},
    },
}

_ID_FATURA = Path(..., description="Identificador da fatura no formato `FAT-{ano}-{sequencial}`.",
                  examples=["FAT-2026-001"])


# ----------------------------------------------------------------------------
# Endpoints (Domínio 7 — PayFlow API)
# ----------------------------------------------------------------------------
@app.post(
    "/api/v1/faturas",
    response_model=FaturaDTO,
    status_code=201,
    tags=["Faturas"],
    summary="Gerar nova fatura de cobrança",
    response_description="Fatura criada com status PENDENTE e o Pix copia-e-cola gerado.",
    responses={
        201: _sucesso("Fatura criada com status PENDENTE e o Pix copia-e-cola gerado.", _FATURA_PENDENTE),
        400: _erro(
            "Dados inválidos: valor_reais <= 0, vencimento no passado, CPF/CNPJ inválido ou campo ausente.",
            ("Vencimento no passado", "VENCIMENTO_NO_PASSADO", "A data de vencimento 2026-01-10 está no passado."),
            ("Valor <= 0, CPF/CNPJ inválido ou campo ausente", "REQUISICAO_INVALIDA",
             "Requisição inválida. valor_reais: Input should be greater than 0"),
        ),
    },
)
def gerar_fatura(
    payload: CriarFaturaDTO = Body(..., openapi_examples=_EXEMPLOS_CRIAR),
    db: Session = Depends(get_db),
) -> FaturaDTO:
    """Cria uma fatura com status **PENDENTE** e devolve o Pix copia-e-cola (BR Code EMV com CRC16).

    - `valor_reais` deve ser maior que zero (arredondado para 2 casas).
    - `data_vencimento` não pode estar no passado; vencer **hoje** é aceito (fuso de Belém).
    - `cliente_cnpj_cpf` aceita CPF ou CNPJ, com ou sem máscara, e é gravado só com dígitos.
    - O ID segue o formato `FAT-{ano}-{sequencial}`.
    """
    return services.criar_fatura(db, payload)


@app.get(
    "/api/v1/clientes/{cnpj_cpf}/extrato",
    response_model=ExtratoClienteDTO,
    status_code=200,
    tags=["Clientes"],
    summary="Consultar extrato do cliente",
    response_description="Faturas do cliente com os totais pendente e pago.",
    responses={
        200: _sucesso("Faturas do cliente com os totais pendente e pago.", {
            "cliente_cnpj_cpf": "52998224725",
            "cliente_nome": "Maria das Dores Souza",
            "total_pendente_reais": 450.00,
            "total_pago_reais": 450.00,
            "faturas": [
                _FATURA_PAGA,
                {**_FATURA_PENDENTE, "id_fatura": "FAT-2026-002"},
                {**_FATURA_PENDENTE, "id_fatura": "FAT-2026-003", "valor_reais": 99.90, "status": "CANCELADA"},
            ],
        }),
        400: _erro(
            "O CPF/CNPJ informado é inválido.",
            ("Documento inválido", "DOCUMENTO_INVALIDO",
             "CPF/CNPJ inválido: informe 11 dígitos (CPF) ou 14 caracteres (CNPJ)."),
        ),
        404: _erro(
            "O cliente não possui faturas no sistema.",
            ("Cliente sem faturas", "CLIENTE_SEM_FATURAS", "O cliente 11144477735 não possui faturas no sistema."),
        ),
    },
)
def consultar_extrato(
    cnpj_cpf: str = Path(
        ...,
        description=(
            "CPF ou CNPJ do cliente. A máscara é ignorada (ex.: `529.982.247-25`); "
            "para CNPJ use só os dígitos, pois a barra da máscara é um separador de rota."
        ),
        examples=["52998224725"],
    ),
    db: Session = Depends(get_db),
) -> ExtratoClienteDTO:
    """Lista todas as faturas do cliente com os totais **pendente** e **pago**.

    - `total_pendente_reais` soma as faturas PENDENTE e `total_pago_reais` as PAGA.
    - Faturas CANCELADAS aparecem na lista, mas não entram nos totais.
    """
    return services.consultar_extrato(db, cnpj_cpf)


@app.put(
    "/api/v1/faturas/{id_fatura}/pagar",
    response_model=FaturaDTO,
    status_code=200,
    tags=["Faturas"],
    summary="Registrar pagamento/liquidação",
    response_description="Fatura liquidada, com status PAGA e data_pagamento preenchida.",
    responses={
        200: _sucesso("Fatura liquidada, com status PAGA e data_pagamento preenchida.", _FATURA_PAGA),
        400: _erro(
            "A fatura não está PENDENTE ou o corpo da requisição é inválido.",
            ("Fatura já paga", "FATURA_JA_PAGA", "A fatura FAT-2026-001 já está PAGA."),
            ("Fatura cancelada", "FATURA_CANCELADA", "A fatura FAT-2026-001 está CANCELADA e não pode ser paga."),
            ("Forma de pagamento inválida", "REQUISICAO_INVALIDA",
             "Requisição inválida. forma_pagamento: Input should be 'PIX' or 'BOLETO'"),
        ),
        404: _ERRO_404_FATURA,
    },
)
def pagar_fatura(
    id_fatura: str = _ID_FATURA,
    payload: PagarFaturaDTO = Body(..., openapi_examples=_EXEMPLOS_PAGAR),
    db: Session = Depends(get_db),
) -> FaturaDTO:
    """Liquida uma fatura **PENDENTE**: muda o status para PAGA e grava `data_pagamento` (UTC).

    `forma_pagamento` aceita somente `PIX` ou `BOLETO`.
    """
    return services.pagar_fatura(db, id_fatura, payload)


@app.delete(
    "/api/v1/faturas/{id_fatura}",
    response_model=CancelamentoDTO,
    status_code=200,
    tags=["Faturas"],
    summary="Cancelar fatura",
    response_description="Fatura cancelada (exclusão lógica).",
    responses={
        200: _sucesso("Fatura cancelada (exclusão lógica).", {
            "mensagem": "Fatura cancelada com sucesso.", "id_fatura": "FAT-2026-001", "status": "CANCELADA",
        }),
        400: _erro(
            "A fatura já foi PAGA ou já está CANCELADA.",
            ("Fatura já paga", "FATURA_JA_PAGA", "A fatura FAT-2026-001 já foi PAGA e não pode ser cancelada."),
            ("Fatura já cancelada", "FATURA_JA_CANCELADA", "A fatura FAT-2026-001 já está CANCELADA."),
        ),
        404: _ERRO_404_FATURA,
    },
)
def cancelar_fatura(id_fatura: str = _ID_FATURA, db: Session = Depends(get_db)) -> CancelamentoDTO:
    """Cancela uma fatura **PENDENTE** (exclusão lógica).

    O registro não é apagado: continua no extrato com status CANCELADA, fora dos totais.
    Faturas PAGAS não podem ser canceladas.
    """
    return services.cancelar_fatura(db, id_fatura)


# ----------------------------------------------------------------------------
# Ajuste do OpenAPI
# ----------------------------------------------------------------------------
def _openapi_sem_422() -> dict:
    """Gera o schema do Swagger sem as respostas 422 automáticas do FastAPI.

    A API nunca devolve 422: o handler global converte erros de validação em
    400 com o JSON padronizado, que já está documentado em cada rota.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    for operacoes in schema.get("paths", {}).values():
        for operacao in operacoes.values():
            operacao.get("responses", {}).pop("422", None)
    esquemas = schema.get("components", {}).get("schemas", {})
    for nome in ("HTTPValidationError", "ValidationError"):
        esquemas.pop(nome, None)
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_sem_422
