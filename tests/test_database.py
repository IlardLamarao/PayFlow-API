"""Testa o modelo ORM e a conversão para DTO (exige sqlalchemy)."""

from datetime import date

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base, Fatura  # noqa: E402
from app.schemas import FaturaDTO, StatusFatura  # noqa: E402


@pytest.fixture()
def sessao():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def test_persiste_fatura_com_valores_padrao(sessao):
    sessao.add(Fatura(
        id_fatura="FAT-2026-1",
        cliente_cnpj_cpf="52998224725",
        cliente_nome="Maria Souza",
        valor_reais=450.0,
        data_vencimento=date(2026, 12, 15),
        descricao="Mensalidade",
        linha_digitavel_pix="000201...",
    ))
    sessao.commit()

    fatura = sessao.query(Fatura).filter_by(id_fatura="FAT-2026-1").one()
    assert fatura.status == "PENDENTE"
    assert fatura.data_emissao is not None
    assert fatura.data_pagamento is None


def test_orm_converte_para_dto_sem_vazar_campos_internos(sessao):
    sessao.add(Fatura(
        id_fatura="FAT-2026-2",
        cliente_cnpj_cpf="52998224725",
        cliente_nome="Maria Souza",
        valor_reais=10.0,
        data_vencimento=date(2026, 12, 15),
        descricao="x",
        linha_digitavel_pix="000201...",
    ))
    sessao.commit()

    dto = FaturaDTO.model_validate(sessao.query(Fatura).one())
    assert dto.status is StatusFatura.PENDENTE
    assert dto.data_emissao.tzinfo is not None
    assert {"id", "cliente_cnpj_cpf", "descricao", "forma_pagamento"}.isdisjoint(dto.model_dump())
