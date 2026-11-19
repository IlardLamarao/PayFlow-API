"""Validação e normalização de CPF e CNPJ.

- CPF: 11 dígitos, com dígitos verificadores (módulo 11).
- CNPJ: 14 caracteres. Desde julho de 2026 a Receita Federal emite CNPJ
  alfanumérico (12 primeiras posições com 0-9 e A-Z, 2 dígitos verificadores
  numéricos), então o validador aceita as duas formas. O cálculo usa o valor
  `ord(caractere) - 48`, que coincide com o dígito nos CNPJs numéricos.

A máscara (`.`, `-`, `/` e espaços) é aceita e removida.
"""

import re

_MASCARA = re.compile(r"[.\-/\s]")
_CNPJ_FORMATO = re.compile(r"[0-9A-Z]{12}[0-9]{2}")

_PESOS_CNPJ_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_2 = [6] + _PESOS_CNPJ_1


def _dv(soma: int) -> int:
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def somente_caracteres(valor: str) -> str:
    """Remove a máscara e padroniza em maiúsculas."""
    return _MASCARA.sub("", valor).upper()


def validar_cpf(valor: str) -> bool:
    cpf = somente_caracteres(valor)
    if len(cpf) != 11 or not cpf.isdigit() or len(set(cpf)) == 1:
        return False
    digitos = [int(c) for c in cpf]
    d1 = _dv(sum(d * p for d, p in zip(digitos[:9], range(10, 1, -1))))
    d2 = _dv(sum(d * p for d, p in zip(digitos[:10], range(11, 1, -1))))
    return digitos[9] == d1 and digitos[10] == d2


def calcular_dv_cnpj(base12: str) -> str:
    """Calcula os 2 dígitos verificadores de uma base de 12 caracteres."""
    valores = [ord(c) - 48 for c in base12]
    d1 = _dv(sum(v * p for v, p in zip(valores, _PESOS_CNPJ_1)))
    valores_13 = valores + [d1]
    d2 = _dv(sum(v * p for v, p in zip(valores_13, _PESOS_CNPJ_2)))
    return f"{d1}{d2}"


def validar_cnpj(valor: str) -> bool:
    cnpj = somente_caracteres(valor)
    if not _CNPJ_FORMATO.fullmatch(cnpj) or len(set(cnpj)) == 1:
        return False
    return cnpj[12:] == calcular_dv_cnpj(cnpj[:12])


def normalizar_documento(valor: str) -> str:
    """Valida um CPF ou CNPJ e devolve só os caracteres, sem máscara.

    Lança `ValueError` (que o Pydantic converte em erro de validação) quando
    o documento não é um CPF nem um CNPJ válido.
    """
    if not isinstance(valor, str):
        raise ValueError("CPF/CNPJ deve ser texto.")
    limpo = somente_caracteres(valor)
    if len(limpo) == 11:
        if validar_cpf(limpo):
            return limpo
        raise ValueError("CPF inválido.")
    if len(limpo) == 14:
        if validar_cnpj(limpo):
            return limpo
        raise ValueError("CNPJ inválido.")
    raise ValueError("CPF/CNPJ inválido: informe 11 dígitos (CPF) ou 14 caracteres (CNPJ).")
