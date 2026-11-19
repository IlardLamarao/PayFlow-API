"""DTOs (Data Transfer Objects) da PayFlow API.

Este é o contrato público do serviço. Nenhuma rota recebe ou devolve
dicionários soltos nem o modelo ORM: tudo passa por estas classes, o que evita
o vazamento da camada de persistência (Abstraction Leakage).
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.validators import normalizar_documento

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class StatusFatura(str, Enum):
    PENDENTE = "PENDENTE"
    PAGA = "PAGA"
    CANCELADA = "CANCELADA"


class FormaPagamento(str, Enum):
    PIX = "PIX"
    BOLETO = "BOLETO"


def _como_utc(valor: Optional[datetime]) -> Optional[datetime]:
    """O SQLite devolve datas sem fuso; a API sempre publica em UTC."""
    if valor is not None and valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor


# ----------------------------------------------------------------------------
# DTOs de entrada
# ----------------------------------------------------------------------------
class CriarFaturaDTO(BaseModel):
    """Dados para gerar uma nova fatura de cobrança."""

    cliente_cnpj_cpf: str = Field(
        ..., description="CPF ou CNPJ do cliente, com ou sem máscara.", examples=["529.982.247-25"]
    )
    cliente_nome: Texto = Field(..., examples=["Maria das Dores Souza"])
    valor_reais: float = Field(..., gt=0, description="Valor da cobrança em reais (> 0).", examples=[450.00])
    data_vencimento: date = Field(..., description="Data de vencimento (YYYY-MM-DD).", examples=["2026-12-15"])
    descricao: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] = Field(
        ..., examples=["Mensalidade de novembro/2026"]
    )

    @field_validator("cliente_cnpj_cpf")
    @classmethod
    def _validar_documento(cls, valor: str) -> str:
        return normalizar_documento(valor)

    @field_validator("valor_reais")
    @classmethod
    def _duas_casas(cls, valor: float) -> float:
        arredondado = round(valor, 2)
        if arredondado <= 0:
            raise ValueError("valor_reais deve ser de pelo menos R$ 0,01.")
        return arredondado


class PagarFaturaDTO(BaseModel):
    """Dados do pagamento/liquidação de uma fatura."""

    forma_pagamento: FormaPagamento = Field(..., description="PIX ou BOLETO.", examples=["PIX"])
    codigo_comprovante: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = Field(
        ..., examples=["TRX998123"]
    )


# ----------------------------------------------------------------------------
# DTOs de saída
# ----------------------------------------------------------------------------
class FaturaDTO(BaseModel):
    """Representação pública de uma fatura."""

    model_config = ConfigDict(from_attributes=True)

    id_fatura: str = Field(..., examples=["FAT-2026-881"])
    cliente_nome: str = Field(..., examples=["Maria das Dores Souza"])
    valor_reais: float = Field(..., examples=[450.00])
    data_vencimento: date = Field(..., examples=["2026-12-15"])
    linha_digitavel_pix: str = Field(..., description="Pix copia-e-cola (BR Code).")
    status: StatusFatura = Field(..., examples=["PENDENTE"])
    data_emissao: datetime = Field(..., examples=["2026-11-19T17:30:00Z"])
    data_pagamento: Optional[datetime] = Field(
        None, description="Preenchida quando a fatura é paga; nula nos demais casos."
    )

    @field_validator("data_emissao", "data_pagamento")
    @classmethod
    def _utc(cls, valor: Optional[datetime]) -> Optional[datetime]:
        return _como_utc(valor)


class ExtratoClienteDTO(BaseModel):
    """Extrato de faturas de um cliente."""

    cliente_cnpj_cpf: str = Field(..., examples=["52998224725"])
    cliente_nome: str = Field(..., examples=["Maria das Dores Souza"])
    total_pendente_reais: float = Field(..., examples=[450.00])
    total_pago_reais: float = Field(..., examples=[1200.00])
    faturas: List[FaturaDTO]


class CancelamentoDTO(BaseModel):
    """Resposta do cancelamento de uma fatura."""

    mensagem: str = Field(..., examples=["Fatura cancelada com sucesso."])
    id_fatura: str = Field(..., examples=["FAT-2026-881"])
    status: StatusFatura = Field(..., examples=["CANCELADA"])


class ErroPadronizadoDTO(BaseModel):
    """Formato único de erro devolvido em qualquer resposta 4xx/5xx."""

    codigo_erro: str = Field(..., examples=["RECURSO_NAO_ENCONTRADO"])
    mensagem: str = Field(..., examples=["Fatura FAT-2026-999 não encontrada."])
    timestamp: str = Field(..., description="Momento do erro em UTC (ISO-8601).", examples=["2026-11-05T14:30:00Z"])

    @classmethod
    def novo(cls, codigo_erro: str, mensagem: str) -> "ErroPadronizadoDTO":
        agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return cls(codigo_erro=codigo_erro, mensagem=mensagem, timestamp=agora)
