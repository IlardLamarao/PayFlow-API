"""Exceções de domínio da PayFlow API.

Os services lançam estas exceções; o handler global em `main.py` as converte
no JSON de erro padronizado (`codigo_erro`, `mensagem`, `timestamp`) com o
status HTTP correto. Assim nenhuma regra de negócio conhece o HTTP.
"""


class ErroDeDominio(Exception):
    """Base das exceções de negócio: carrega status HTTP e código de erro."""

    status_code: int = 400
    codigo_erro_padrao: str = "REQUISICAO_INVALIDA"

    def __init__(self, mensagem: str, codigo_erro: str | None = None) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo_erro = codigo_erro or self.codigo_erro_padrao


class RequisicaoInvalidaError(ErroDeDominio):
    """400 Bad Request: regra de validação ou de estado violada."""

    status_code = 400
    codigo_erro_padrao = "REQUISICAO_INVALIDA"


class RecursoNaoEncontradoError(ErroDeDominio):
    """404 Not Found: fatura ou cliente inexistente."""

    status_code = 404
    codigo_erro_padrao = "RECURSO_NAO_ENCONTRADO"


class ConflitoError(ErroDeDominio):
    """409 Conflict: o estado atual do recurso impede a operação."""

    status_code = 409
    codigo_erro_padrao = "CONFLITO"
