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
├── main.py         # app FastAPI, Swagger e tratamento global de erros
├── schemas.py      # DTOs de entrada, saída e erro
├── services.py     # regras de negócio (Parte 2)
├── database.py     # engine SQLite e modelo ORM
├── exceptions.py   # exceções de domínio (400/404/409)
├── validators.py   # validação de CPF/CNPJ
└── pix.py          # gerador de BR Code (Pix copia-e-cola) com CRC16
tests/
```

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
- [ ] **Parte 2:** services e os 4 endpoints
- [ ] **Parte 3:** coleção Postman, revisão do Swagger e README final
