# PayFlow API

API RESTful de faturamento e cobranças Pix/Boleto da fintech **PayFlow Gestão**
(Domínio 7). Projeto do Marco 1 da disciplina *Computação em Nuvem e Arquitetura
Orientada a Serviços (SOA)*, IFPA Campus Ananindeua.

**Stack:** Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2 + SQLite, pytest.

- Persistência em **SQLite** (arquivo `payflow.db`, criado automaticamente).
- Pix copia-e-cola no padrão **BR Code EMV** do Banco Central, com **CRC16-CCITT**.
- CPF/CNPJ validados pelos **dígitos verificadores**, com ou sem máscara.
- Erros sempre no formato `{codigo_erro, mensagem, timestamp}`, com **400** no lugar do 422 e sem stack trace.

## Como executar

```bash
git clone https://github.com/IlardLamarao/PayFlow-API.git
cd PayFlow-API

python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt

uvicorn app.main:app --reload
```

| Recurso | Endereço |
|---|---|
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| OpenAPI (JSON) | http://127.0.0.1:8000/openapi.json |

### Variáveis de ambiente (opcionais)

| Variável | Padrão | Uso |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./payflow.db` | Banco de dados |
| `PIX_CHAVE` | chave aleatória fictícia | Chave Pix do recebedor no BR Code |
| `PIX_RECEBEDOR` | `PAYFLOW GESTAO` | Nome do recebedor no BR Code |
| `PIX_CIDADE` | `BELEM` | Cidade do recebedor no BR Code |

Para zerar os dados, pare a API e apague o arquivo `payflow.db`.

## Como testar

### Testes automatizados (pytest)

```bash
pytest -v
```

Cada teste de endpoint roda num SQLite em memória isolado, sem tocar no
`payflow.db`. A suíte cobre:

| Arquivo | O que testa |
|---|---|
| `tests/test_validators.py` | CPF/CNPJ: dígitos verificadores, máscara e CNPJ alfanumérico |
| `tests/test_pix.py` | Montagem do BR Code EMV e CRC16 |
| `tests/test_schemas.py` | Validações dos DTOs |
| `tests/test_database.py` | Modelo ORM e persistência |
| `tests/test_erros.py` | Formato padronizado de erro (400 no lugar de 422, sem stack trace) |
| `tests/test_endpoints.py` | Sucesso e erro dos 4 endpoints |
| `tests/test_bordas.py` | Bordas: CNPJ com máscara, extrato com canceladas, vencimento hoje, contrato do Swagger |

### Postman

1. Importe no Postman os dois arquivos da raiz do projeto:
   - `PayFlow-API-Collection.postman_collection.json` (coleção)
   - `PayFlow-API-Local.postman_environment.json` (ambiente com `base_url`)
2. Selecione o ambiente **PayFlow API - Local** e suba a API.
3. Rode a coleção inteira no **Collection Runner**, na ordem das pastas.

A coleção tem 21 requisições com casos **200/201/400/404** de cada endpoint e
testes automáticos em cada uma. As requisições de criação salvam os IDs gerados
em variáveis (`id_fatura`, `id_fatura_cnpj`, `id_fatura_cancelar`) usadas pelas
seguintes, e as datas de vencimento (hoje, futuro, passado) são calculadas num
script de pré-requisição, então a coleção funciona em qualquer dia.

## Endpoints

| Verbo | Rota | Sucesso | Erros |
|---|---|---|---|
| POST | `/api/v1/faturas` | 201 + `FaturaDTO` com Pix | 400 (valor <= 0, vencimento no passado, CPF/CNPJ inválido, campo ausente) |
| GET | `/api/v1/clientes/{cnpj_cpf}/extrato` | 200 + `ExtratoClienteDTO` | 400 (documento inválido), 404 (cliente sem faturas) |
| PUT | `/api/v1/faturas/{id_fatura}/pagar` | 200 + `FaturaDTO` (PAGA) | 400 (já PAGA/CANCELADA, forma de pagamento inválida), 404 |
| DELETE | `/api/v1/faturas/{id_fatura}` | 200 + `CancelamentoDTO` | 400 (já PAGA ou CANCELADA), 404 |

Ciclo de vida da fatura: `PENDENTE` → `PAGA` ou `PENDENTE` → `CANCELADA`.

## Exemplos com curl

> No Windows, rode os exemplos no Git Bash ou WSL. No PowerShell, troque `curl` por `curl.exe`
> e ajuste as aspas do JSON.

**Gerar fatura (201):**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/faturas \
  -H "Content-Type: application/json" \
  -d '{
        "cliente_cnpj_cpf": "529.982.247-25",
        "cliente_nome": "Maria das Dores Souza",
        "valor_reais": 450.00,
        "data_vencimento": "2026-12-15",
        "descricao": "Mensalidade de novembro/2026"
      }'
```

```json
{
  "id_fatura": "FAT-2026-001",
  "cliente_nome": "Maria das Dores Souza",
  "valor_reais": 450.0,
  "data_vencimento": "2026-12-15",
  "linha_digitavel_pix": "00020101021226580014br.gov.bcb.pix0136...6304XXXX",
  "status": "PENDENTE",
  "data_emissao": "2026-11-19T17:30:00Z",
  "data_pagamento": null
}
```

**Consultar extrato (200):**

```bash
curl http://127.0.0.1:8000/api/v1/clientes/52998224725/extrato
```

```json
{
  "cliente_cnpj_cpf": "52998224725",
  "cliente_nome": "Maria das Dores Souza",
  "total_pendente_reais": 450.0,
  "total_pago_reais": 0.0,
  "faturas": [ { "id_fatura": "FAT-2026-001", "status": "PENDENTE", "...": "..." } ]
}
```

**Registrar pagamento (200):**

```bash
curl -X PUT http://127.0.0.1:8000/api/v1/faturas/FAT-2026-001/pagar \
  -H "Content-Type: application/json" \
  -d '{"forma_pagamento": "PIX", "codigo_comprovante": "TRX998123"}'
```

**Cancelar fatura (200):**

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/faturas/FAT-2026-002
```

```json
{"mensagem": "Fatura cancelada com sucesso.", "id_fatura": "FAT-2026-002", "status": "CANCELADA"}
```

**Erro: vencimento no passado (400):**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/faturas \
  -H "Content-Type: application/json" \
  -d '{"cliente_cnpj_cpf": "52998224725", "cliente_nome": "Maria", "valor_reais": 10, "data_vencimento": "2026-01-10", "descricao": "Teste"}'
```

```json
{"codigo_erro": "VENCIMENTO_NO_PASSADO", "mensagem": "A data de vencimento 2026-01-10 está no passado.", "timestamp": "2026-11-19T14:30:00Z"}
```

**Erro: fatura inexistente (404):**

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/faturas/FAT-2026-999
```

```json
{"codigo_erro": "FATURA_NAO_ENCONTRADA", "mensagem": "Fatura FAT-2026-999 não encontrada.", "timestamp": "2026-11-19T14:30:00Z"}
```

## Formato de erro

Toda resposta de erro segue o mesmo JSON, sem stack trace:

```json
{"codigo_erro": "RECURSO_NAO_ENCONTRADO", "mensagem": "Descrição clara do erro.", "timestamp": "2026-11-05T14:30:00Z"}
```

| `codigo_erro` | Status | Quando |
|---|---|---|
| `REQUISICAO_INVALIDA` | 400 | Corpo inválido: campo ausente, tipo errado, valor <= 0, CPF/CNPJ inválido, forma de pagamento fora de PIX/BOLETO, JSON malformado |
| `VENCIMENTO_NO_PASSADO` | 400 | `data_vencimento` anterior a hoje |
| `DOCUMENTO_INVALIDO` | 400 | CPF/CNPJ inválido na URL do extrato |
| `FATURA_JA_PAGA` | 400 | Pagar ou cancelar uma fatura PAGA |
| `FATURA_CANCELADA` | 400 | Pagar uma fatura CANCELADA |
| `FATURA_JA_CANCELADA` | 400 | Cancelar uma fatura já CANCELADA |
| `CLIENTE_SEM_FATURAS` | 404 | Extrato de cliente sem faturas |
| `FATURA_NAO_ENCONTRADA` | 404 | ID de fatura inexistente |
| `RECURSO_NAO_ENCONTRADO` | 404 | Rota inexistente |
| `ERRO_INTERNO` | 500 | Erro inesperado (detalhe só no log do servidor) |

## Decisões de especificação

- Cancelar fatura já CANCELADA retorna 400 (a ficha só proíbe cancelar fatura PAGA).
- `forma_pagamento` aceita somente `PIX` e `BOLETO`; outro valor retorna 400.
- Erros de validação do FastAPI (422 por padrão) viram 400 com o JSON padrão; o 422 também foi removido da documentação do Swagger.
- ID da fatura no formato `FAT-{ano}-{sequencial}`; a busca por ID ignora maiúsculas/minúsculas.
- `FaturaDTO` tem o campo opcional `data_pagamento` (null enquanto a fatura não é paga).
- CPF/CNPJ aceito com ou sem máscara e gravado só com dígitos; a busca do extrato ignora a máscara.
  Na URL do extrato, o CNPJ deve ir só com dígitos, pois a barra da máscara (`/`) é separador de rota.
- Extrato: `total_pendente_reais` soma as PENDENTE e `total_pago_reais` as PAGA; as CANCELADA aparecem na lista, mas ficam fora dos totais.
- Vencimento no passado retorna 400; vencimento hoje é válido ("hoje" no fuso de Belém, UTC-3).
- Chave Pix fictícia, com recebedor `PAYFLOW GESTAO` e cidade `BELEM`.

## Estrutura do projeto

```
PayFlow-API/
├── app/
│   ├── main.py         # app FastAPI, os 4 endpoints, Swagger e tratamento global de erros
│   ├── schemas.py      # DTOs de entrada, saída e erro
│   ├── services.py     # regras de negócio (criar, extrato, pagar, cancelar)
│   ├── database.py     # engine SQLite, sessão e modelo ORM
│   ├── exceptions.py   # exceções de domínio (400/404/409)
│   ├── validators.py   # validação de CPF/CNPJ
│   └── pix.py          # gerador de BR Code (Pix copia-e-cola) com CRC16
├── tests/              # testes pytest (unidade, endpoints e bordas)
├── PayFlow-API-Collection.postman_collection.json
├── PayFlow-API-Local.postman_environment.json
├── requirements.txt
├── pytest.ini
└── README.md
```

## Checklist do Marco 1

- [x] **Histórico Git:** 3 commits, um por integrante (fundação, endpoints, documentação)
- [x] **4 endpoints** da ficha com verbos, rotas e status codes corretos (201/200/400/404)
- [x] **DTOs** em todas as entradas e saídas, sem expor o modelo ORM
- [x] **Erros padronizados** `{codigo_erro, mensagem, timestamp}`, 400 no lugar de 422, sem stack trace
- [x] **Documentação:** Swagger em `/docs` com exemplos e coleção Postman exportada na raiz

## Divisão do trabalho

- [x] **Parte 1 (Integrante 1):** base do projeto, DTOs, banco, validadores, gerador Pix e erros globais
- [x] **Parte 2 (Integrante 2):** services e os 4 endpoints
- [x] **Parte 3 (Integrante 3):** coleção Postman, revisão do Swagger, testes de borda e README final
