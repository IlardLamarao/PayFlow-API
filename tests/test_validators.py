import pytest

from app.validators import (
    calcular_dv_cnpj,
    normalizar_documento,
    validar_cnpj,
    validar_cpf,
)


def test_cpf_valido_com_e_sem_mascara():
    assert validar_cpf("529.982.247-25")
    assert validar_cpf("52998224725")


@pytest.mark.parametrize(
    "cpf",
    ["529.982.247-24", "111.111.111-11", "000.000.000-00", "1234", "5299822472a", ""],
)
def test_cpf_invalido(cpf):
    assert not validar_cpf(cpf)


def test_cnpj_numerico_valido_com_e_sem_mascara():
    assert validar_cnpj("11.222.333/0001-81")
    assert validar_cnpj("11222333000181")


@pytest.mark.parametrize(
    "cnpj",
    ["11.222.333/0001-82", "00000000000000", "11111111111111", "1122233300018", ""],
)
def test_cnpj_invalido(cnpj):
    assert not validar_cnpj(cnpj)


def test_cnpj_alfanumerico_valido():
    base = "12ABC34501DE"
    cnpj = base + calcular_dv_cnpj(base)
    assert validar_cnpj(cnpj)
    assert validar_cnpj(cnpj.lower())
    # Trocar um dígito verificador invalida o documento.
    errado = base + ("00" if calcular_dv_cnpj(base) != "00" else "11")
    assert not validar_cnpj(errado)


def test_normalizar_remove_mascara_e_padroniza():
    assert normalizar_documento("529.982.247-25") == "52998224725"
    assert normalizar_documento(" 11.222.333/0001-81 ") == "11222333000181"


@pytest.mark.parametrize("entrada", ["123", "529.982.247-24", "11.222.333/0001-82", "abc"])
def test_normalizar_rejeita_invalidos(entrada):
    with pytest.raises(ValueError):
        normalizar_documento(entrada)
