"""Gerador de Pix "copia e cola" (BR Code EMV) com CRC16.

Segue o formato EMV QRCPS do Banco Central: cada campo é `ID` (2 dígitos) +
`tamanho` (2 dígitos) + valor, e o payload termina com o campo 63 (CRC16
CCITT-FALSE, polinômio 0x1021, valor inicial 0xFFFF).

A chave Pix e o recebedor são FICTÍCIOS (projeto acadêmico): o código gerado
tem estrutura válida, mas não move dinheiro real. Podem ser trocados pelas
variáveis de ambiente PIX_CHAVE, PIX_RECEBEDOR e PIX_CIDADE.
"""

import os
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

CHAVE_PIX_PADRAO = "5f9c1f4e-8d3a-4b7e-9a21-0c6d2e7b4a11"
RECEBEDOR_PADRAO = "PAYFLOW GESTAO"
CIDADE_PADRAO = "BELEM"


def crc16_ccitt(dados: str) -> str:
    """CRC16 CCITT-FALSE em hexadecimal maiúsculo com 4 dígitos."""
    crc = 0xFFFF
    for byte in dados.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def _campo(identificador: str, valor: str) -> str:
    if len(valor) > 99:
        raise ValueError(f"Campo Pix {identificador} excede 99 caracteres.")
    return f"{identificador}{len(valor):02d}{valor}"


def _ascii(texto: str, limite: int) -> str:
    """Remove acentos e caracteres fora do ASCII imprimível, em maiúsculas."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r"[^A-Za-z0-9 .,\-]", "", sem_acento).strip().upper()
    return limpo[:limite]


def _txid(id_fatura: str) -> str:
    """O txid aceita só letras e números (até 25): 'FAT-2026-881' -> 'FAT2026881'."""
    return re.sub(r"[^A-Za-z0-9]", "", id_fatura)[:25] or "***"


def gerar_br_code(
    valor_reais: float,
    id_fatura: str,
    descricao: str | None = None,
    chave: str | None = None,
    recebedor: str | None = None,
    cidade: str | None = None,
) -> str:
    """Monta o payload Pix copia-e-cola de uma cobrança."""
    valor = Decimal(str(valor_reais)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if valor <= 0:
        raise ValueError("O valor do Pix deve ser maior que zero.")

    chave = chave or os.getenv("PIX_CHAVE", CHAVE_PIX_PADRAO)
    recebedor = recebedor or os.getenv("PIX_RECEBEDOR", RECEBEDOR_PADRAO)
    cidade = cidade or os.getenv("PIX_CIDADE", CIDADE_PADRAO)

    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave)
    if descricao:
        # O campo 26 inteiro cabe em 99 caracteres; a descrição usa o que sobrar.
        sobra = 99 - len(conta) - 4
        texto = _ascii(descricao, max(sobra, 0))
        if texto:
            conta += _campo("02", texto)

    payload = (
        _campo("00", "01")
        + _campo("01", "12")  # 12 = cobrança de uso único
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")  # BRL
        + _campo("54", f"{valor:.2f}")
        + _campo("58", "BR")
        + _campo("59", _ascii(recebedor, 25))
        + _campo("60", _ascii(cidade, 15))
        + _campo("62", _campo("05", _txid(id_fatura)))
        + "6304"
    )
    return payload + crc16_ccitt(payload)
