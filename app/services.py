"""Camada de regras de negócio da PayFlow API.

Os services recebem DTOs de entrada, aplicam as regras da ficha do domínio,
conversam com o banco pela sessão recebida e devolvem DTOs de saída. Quando
uma regra é violada, lançam uma exceção de domínio (`app.exceptions`); o
handler global em `main.py` a transforma no JSON de erro padronizado.

Nada aqui conhece HTTP, e o modelo ORM nunca sai desta camada.
"""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Fatura
from app.exceptions import RecursoNaoEncontradoError, RequisicaoInvalidaError
from app.pix import gerar_br_code
from app.schemas import (
    CancelamentoDTO,
    CriarFaturaDTO,
    ExtratoClienteDTO,
    FaturaDTO,
    PagarFaturaDTO,
    StatusFatura,
)
from app.validators import normalizar_documento

# Belém não tem horário de verão: UTC-3 fixo. Usado para decidir o que é "hoje"
# na regra de vencimento, independente do fuso do servidor.
FUSO_BELEM = timezone(timedelta(hours=-3), "America/Belem")


def hoje_em_belem() -> date:
    return datetime.now(FUSO_BELEM).date()


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _buscar_fatura(db: Session, id_fatura: str) -> Fatura:
    fatura = db.scalar(select(Fatura).where(Fatura.id_fatura == id_fatura.strip().upper()))
    if fatura is None:
        raise RecursoNaoEncontradoError(
            f"Fatura {id_fatura} não encontrada.", codigo_erro="FATURA_NAO_ENCONTRADA"
        )
    return fatura


# ----------------------------------------------------------------------------
# POST /api/v1/faturas
# ----------------------------------------------------------------------------
def criar_fatura(db: Session, dados: CriarFaturaDTO) -> FaturaDTO:
    """Gera uma fatura PENDENTE com ID `FAT-{ano}-{sequencial}` e Pix copia-e-cola.

    Regras: valor_reais > 0 (garantido pelo DTO), CPF/CNPJ válido (DTO) e
    vencimento não pode estar no passado (hoje é aceito).
    """
    if dados.data_vencimento < hoje_em_belem():
        raise RequisicaoInvalidaError(
            f"A data de vencimento {dados.data_vencimento.isoformat()} está no passado.",
            codigo_erro="VENCIMENTO_NO_PASSADO",
        )

    emissao = _agora_utc()
    fatura = Fatura(
        id_fatura=f"TMP-{uuid4().hex[:12]}",  # provisório até o banco gerar o sequencial
        cliente_cnpj_cpf=dados.cliente_cnpj_cpf,  # já normalizado pelo DTO
        cliente_nome=dados.cliente_nome,
        valor_reais=dados.valor_reais,
        data_vencimento=dados.data_vencimento,
        descricao=dados.descricao,
        linha_digitavel_pix="",
        status=StatusFatura.PENDENTE.value,
        data_emissao=emissao,
    )
    db.add(fatura)
    db.flush()  # obtém o id autoincremento sem fechar a transação

    fatura.id_fatura = f"FAT-{emissao.astimezone(FUSO_BELEM).year}-{fatura.id:03d}"
    fatura.linha_digitavel_pix = gerar_br_code(
        valor_reais=fatura.valor_reais,
        id_fatura=fatura.id_fatura,
        descricao=fatura.descricao,
    )
    db.commit()
    db.refresh(fatura)
    return FaturaDTO.model_validate(fatura)


# ----------------------------------------------------------------------------
# GET /api/v1/clientes/{cnpj_cpf}/extrato
# ----------------------------------------------------------------------------
def consultar_extrato(db: Session, cnpj_cpf: str) -> ExtratoClienteDTO:
    """Lista as faturas do cliente e soma os totais pendente e pago.

    Faturas CANCELADAS aparecem na lista, mas ficam fora dos dois totais.
    """
    try:
        documento = normalizar_documento(cnpj_cpf)
    except ValueError as erro:
        raise RequisicaoInvalidaError(str(erro), codigo_erro="DOCUMENTO_INVALIDO") from erro

    faturas = db.scalars(
        select(Fatura)
        .where(Fatura.cliente_cnpj_cpf == documento)
        .order_by(Fatura.data_emissao, Fatura.id)
    ).all()
    if not faturas:
        raise RecursoNaoEncontradoError(
            f"O cliente {cnpj_cpf} não possui faturas no sistema.",
            codigo_erro="CLIENTE_SEM_FATURAS",
        )

    total_pendente = sum(f.valor_reais for f in faturas if f.status == StatusFatura.PENDENTE.value)
    total_pago = sum(f.valor_reais for f in faturas if f.status == StatusFatura.PAGA.value)

    return ExtratoClienteDTO(
        cliente_cnpj_cpf=documento,
        cliente_nome=faturas[-1].cliente_nome,  # nome da fatura mais recente
        total_pendente_reais=round(total_pendente, 2),
        total_pago_reais=round(total_pago, 2),
        faturas=[FaturaDTO.model_validate(f) for f in faturas],
    )


# ----------------------------------------------------------------------------
# PUT /api/v1/faturas/{id_fatura}/pagar
# ----------------------------------------------------------------------------
def pagar_fatura(db: Session, id_fatura: str, dados: PagarFaturaDTO) -> FaturaDTO:
    """Liquida uma fatura PENDENTE e grava a data de pagamento."""
    fatura = _buscar_fatura(db, id_fatura)

    if fatura.status == StatusFatura.PAGA.value:
        raise RequisicaoInvalidaError(
            f"A fatura {fatura.id_fatura} já está PAGA.", codigo_erro="FATURA_JA_PAGA"
        )
    if fatura.status == StatusFatura.CANCELADA.value:
        raise RequisicaoInvalidaError(
            f"A fatura {fatura.id_fatura} está CANCELADA e não pode ser paga.",
            codigo_erro="FATURA_CANCELADA",
        )

    fatura.status = StatusFatura.PAGA.value
    fatura.data_pagamento = _agora_utc()
    fatura.forma_pagamento = dados.forma_pagamento.value
    fatura.codigo_comprovante = dados.codigo_comprovante
    db.commit()
    db.refresh(fatura)
    return FaturaDTO.model_validate(fatura)


# ----------------------------------------------------------------------------
# DELETE /api/v1/faturas/{id_fatura}
# ----------------------------------------------------------------------------
def cancelar_fatura(db: Session, id_fatura: str) -> CancelamentoDTO:
    """Cancela (exclusão lógica) uma fatura PENDENTE."""
    fatura = _buscar_fatura(db, id_fatura)

    if fatura.status == StatusFatura.PAGA.value:
        raise RequisicaoInvalidaError(
            f"A fatura {fatura.id_fatura} já foi PAGA e não pode ser cancelada.",
            codigo_erro="FATURA_JA_PAGA",
        )
    if fatura.status == StatusFatura.CANCELADA.value:
        raise RequisicaoInvalidaError(
            f"A fatura {fatura.id_fatura} já está CANCELADA.", codigo_erro="FATURA_JA_CANCELADA"
        )

    fatura.status = StatusFatura.CANCELADA.value
    db.commit()
    return CancelamentoDTO(
        mensagem="Fatura cancelada com sucesso.",
        id_fatura=fatura.id_fatura,
        status=StatusFatura.CANCELADA,
    )
