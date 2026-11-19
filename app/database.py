"""Camada de persistência: SQLite via SQLAlchemy 2.0.

O modelo ORM `Fatura` vive só aqui e em `services.py`. As rotas nunca o
recebem nem o devolvem: a conversão para DTO acontece em `schemas.py`.
"""

import os
from datetime import date, datetime, timezone
from typing import Iterator, Optional

from sqlalchemy import Date, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./payflow.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Fatura(Base):
    """Fatura de cobrança. Cancelar não apaga: muda o status para CANCELADA."""

    __tablename__ = "faturas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_fatura: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    cliente_cnpj_cpf: Mapped[str] = mapped_column(String(14), index=True)  # só caracteres, sem máscara
    cliente_nome: Mapped[str] = mapped_column(String(120))
    valor_reais: Mapped[float] = mapped_column(Float)
    data_vencimento: Mapped[date] = mapped_column(Date)
    descricao: Mapped[str] = mapped_column(String(255))
    linha_digitavel_pix: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(10), default="PENDENTE")
    data_emissao: Mapped[datetime] = mapped_column(DateTime, default=_agora_utc)
    data_pagamento: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    forma_pagamento: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    codigo_comprovante: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


def init_db() -> None:
    """Cria as tabelas se ainda não existirem."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """Dependência do FastAPI: uma sessão por requisição (sem estado compartilhado)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
