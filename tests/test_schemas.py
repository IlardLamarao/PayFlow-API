import re
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas import (
    CriarFaturaDTO,
    ErroPadronizadoDTO,
    FaturaDTO,
    FormaPagamento,
    PagarFaturaDTO,
    StatusFatura,
)


def _payload(**extra):
    base = {
        "cliente_cnpj_cpf": "529.982.247-25",
        "cliente_nome": "  Maria Souza  ",
        "valor_reais": 450.0,
        "data_vencimento": "2026-12-15",
        "descricao": "Mensalidade",
    }
    base.update(extra)
    return base


def test_criar_fatura_valida_normaliza_campos():
    dto = CriarFaturaDTO(**_payload())
    assert dto.cliente_cnpj_cpf == "52998224725"
    assert dto.cliente_nome == "Maria Souza"
    assert dto.data_vencimento == date(2026, 12, 15)


@pytest.mark.parametrize("valor", [0, -1, 0.004])
def test_criar_fatura_rejeita_valor_nao_positivo(valor):
    with pytest.raises(ValidationError):
        CriarFaturaDTO(**_payload(valor_reais=valor))


def test_criar_fatura_rejeita_documento_invalido():
    with pytest.raises(ValidationError):
        CriarFaturaDTO(**_payload(cliente_cnpj_cpf="111.111.111-11"))


@pytest.mark.parametrize("campo", ["cliente_nome", "descricao", "data_vencimento", "cliente_cnpj_cpf", "valor_reais"])
def test_criar_fatura_campos_obrigatorios(campo):
    dados = _payload()
    dados.pop(campo)
    with pytest.raises(ValidationError):
        CriarFaturaDTO(**dados)


def test_criar_fatura_rejeita_nome_e_descricao_vazios():
    with pytest.raises(ValidationError):
        CriarFaturaDTO(**_payload(cliente_nome="   "))
    with pytest.raises(ValidationError):
        CriarFaturaDTO(**_payload(descricao=""))


def test_pagar_aceita_somente_pix_e_boleto():
    assert PagarFaturaDTO(forma_pagamento="PIX", codigo_comprovante="TRX1").forma_pagamento is FormaPagamento.PIX
    assert PagarFaturaDTO(forma_pagamento="BOLETO", codigo_comprovante="TRX1").forma_pagamento is FormaPagamento.BOLETO
    with pytest.raises(ValidationError):
        PagarFaturaDTO(forma_pagamento="CARTAO", codigo_comprovante="TRX1")
    with pytest.raises(ValidationError):
        PagarFaturaDTO(forma_pagamento="PIX", codigo_comprovante="")


def test_fatura_dto_converte_objeto_e_publica_datas_em_utc():
    orm = SimpleNamespace(
        id=1,  # campo interno: não pode vazar para o DTO
        id_fatura="FAT-2026-1",
        cliente_nome="Maria Souza",
        valor_reais=450.0,
        data_vencimento=date(2026, 12, 15),
        linha_digitavel_pix="000201...",
        status="PENDENTE",
        data_emissao=datetime(2026, 11, 19, 17, 30),  # sem fuso, como o SQLite devolve
        data_pagamento=None,
        cliente_cnpj_cpf="52998224725",  # também interno
    )
    dto = FaturaDTO.model_validate(orm)
    assert dto.status is StatusFatura.PENDENTE
    assert dto.data_emissao.tzinfo == timezone.utc
    assert dto.data_pagamento is None
    saida = dto.model_dump(mode="json")
    assert "id" not in saida and "cliente_cnpj_cpf" not in saida
    assert saida["data_emissao"].endswith("Z")


def test_erro_padronizado_tem_tres_campos_e_timestamp_utc():
    erro = ErroPadronizadoDTO.novo("RECURSO_NAO_ENCONTRADO", "Fatura não encontrada.")
    corpo = erro.model_dump()
    assert set(corpo) == {"codigo_erro", "mensagem", "timestamp"}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", corpo["timestamp"])
