# PayFlow API

API RESTful de faturamento e cobranças Pix/Boleto da fintech **PayFlow Gestão**
(Domínio 7). Projeto do Marco 1 da disciplina *Computação em Nuvem e Arquitetura
Orientada a Serviços (SOA)*, IFPA Campus Ananindeua.

**Stack:** FastAPI, Pydantic, SQLAlchemy + SQLite, pytest.

## Como executar

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- Os dados ficam em `payflow.db` (SQLite, criado automaticamente). Para usar outro
  banco: variável de ambiente `DATABASE_URL`.

## Testes

```bash
pytest
```

## Estrutura

```
app/
├── main.py         # app FastAPI, os 4 endpoints, Swagger e tratamento global de erros
├── schemas.py      # DTOs de entrada, saída e erro
├── services.py     # regras de negócio (criar, extrato, pagar, cancelar)
├── database.py     # engine SQLite e modelo ORM
├── exceptions.py   # exceções de domínio (400/404/409)
├── validators.py   # validação de CPF/CNPJ
└── pix.py          # gerador de BR Code (Pix copia-e-cola) com CRC16
tests/
```

## Endpoints

| Verbo | Rota | Sucesso | Erros |
|---|---|---|---|
| POST | `/api/v1/faturas` | 201 + `FaturaDTO` com Pix | 400 (valor <= 0, vencimento no passado, CPF/CNPJ inválido) |
| GET | `/api/v1/clientes/{cnpj_cpf}/extrato` | 200 + `ExtratoClienteDTO` | 400 (documento inválido), 404 (cliente sem faturas) |
| PUT | `/api/v1/faturas/{id_fatura}/pagar` | 200 + `FaturaDTO` (PAGA) | 400 (já PAGA/CANCELADA, forma de pagamento inválida), 404 |
| DELETE | `/api/v1/faturas/{id_fatura}` | 200 + `CancelamentoDTO` | 400 (já PAGA ou CANCELADA), 404 |

## Formato de erro

Toda resposta de erro segue o mesmo JSON, sem stack trace:

```json
{"codigo_erro": "RECURSO_NAO_ENCONTRADO", "mensagem": "Descrição clara do erro.", "timestamp": "2026-11-05T14:30:00Z"}
```

Erros de validação de entrada retornam **400** (e não o 422 padrão do FastAPI),
como exige a ficha do domínio.

## Configuração do Pix (opcional)

A chave Pix e o recebedor são fictícios. Para alterar:
`PIX_CHAVE`, `PIX_RECEBEDOR` e `PIX_CIDADE`.

## Status do desenvolvimento

- [x] **Parte 1:** base do projeto, DTOs, banco, validadores, gerador Pix e erros globais
- [x] **Parte 2:** services e os 4 endpoints
- [ ] **Parte 3:** coleção Postman, revisão do Swagger e README final
