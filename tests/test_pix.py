import pytest

from app.pix import crc16_ccitt, gerar_br_code


def _ler_tlv(texto: str) -> dict:
    campos, i = {}, 0
    while i < len(texto):
        identificador = texto[i : i + 2]
        tamanho = int(texto[i + 2 : i + 4])
        campos[identificador] = texto[i + 4 : i + 4 + tamanho]
        i += 4 + tamanho
    return campos


def test_crc16_vetor_conhecido():
    # Vetor de teste padrão do CRC-16/CCITT-FALSE.
    assert crc16_ccitt("123456789") == "29B1"


def test_br_code_estrutura_e_crc():
    codigo = gerar_br_code(150, "FAT-2026-881", descricao="Mensalidade de novembro")
    assert codigo.startswith("000201")
    corpo, crc = codigo[:-4], codigo[-4:]
    assert corpo.endswith("6304")
    assert crc == crc16_ccitt(corpo)

    campos = _ler_tlv(codigo)
    assert campos["53"] == "986"
    assert campos["54"] == "150.00"
    assert campos["58"] == "BR"
    assert campos["59"] == "PAYFLOW GESTAO"
    assert campos["60"] == "BELEM"
    assert campos["63"] == crc
    assert _ler_tlv(campos["62"])["05"] == "FAT2026881"
    conta = _ler_tlv(campos["26"])
    assert conta["00"] == "br.gov.bcb.pix"
    assert conta["01"]
    assert len(campos["26"]) <= 99


def test_br_code_remove_acentos_e_respeita_limites():
    codigo = gerar_br_code(
        10.5, "FAT-2026-1", descricao="Ação de cobrança " * 20, recebedor="João da Conceição Ltda Comércio", cidade="São João de Pirabas"
    )
    campos = _ler_tlv(codigo)
    assert campos["54"] == "10.50"
    assert campos["59"].isascii() and len(campos["59"]) <= 25
    assert campos["60"].isascii() and len(campos["60"]) <= 15
    assert len(campos["26"]) <= 99


def test_br_code_arredonda_valor():
    assert _ler_tlv(gerar_br_code(10.005, "FAT-2026-2"))["54"] == "10.01"


@pytest.mark.parametrize("valor", [0, -5, 0.001])
def test_br_code_rejeita_valor_nao_positivo(valor):
    with pytest.raises(ValueError):
        gerar_br_code(valor, "FAT-2026-3")
