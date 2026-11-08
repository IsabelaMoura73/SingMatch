# SingMatch — repositório de implementação (Dia 1)

Monorepo para o MVP da disciplina de Criatividade Computacional.
Este **não** é o repositório do protótipo estático do PF 2.

> **Etapa 7 (catálogo e letras):** o catálogo passou de 5 para dezenas de forrós, montado a partir
> dos datasets BYRM e UFMG, e o player mostra a letra sincronizada sobre o vídeo original.
> Ver [`docs/ETAPA7_CATALOGO_E_LETRAS.md`](docs/ETAPA7_CATALOGO_E_LETRAS.md).
> As seções abaixo descrevem o Dia 1 e estão parcialmente desatualizadas.

## O que já funciona neste pacote

- Organização de pastas para quatro frentes (dados, IA, backend, frontend).
- API FastAPI: `GET /api/health`.
- Frontend React + Vite: página inicial que consulta `/api/health`.
- PostgreSQL local opcional via Docker Compose (o banco ainda não tem tabelas).
- Cinco músicas do piloto com IDs de vídeos testados anteriormente pela equipe.
- Validador local de integridade básica do JSON.

**Ainda não implementado:** criar/entrar em sala, autenticação por token, persistência,
interpretação GPT, geração de roteiro, edição e player. Esses itens virão nas próximas etapas.

## 1. Preparar ambiente (Ubuntu)

Requisitos: Python 3, Node.js compatível com Vite 7 (20.19+ ou 22.12+), npm e Git.
Docker com Compose é opcional nesta primeira etapa, mas necessário para testar PostgreSQL local.

```bash
cp .env.example .env
python3 scripts/validate_seed.py
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

Abrir `http://127.0.0.1:5173` (frontend) e `http://127.0.0.1:8000/api/health` (API).
O Vite redireciona `/api` ao backend durante o desenvolvimento.

## 2. PostgreSQL local (pode ficar para a próxima etapa)

```bash
docker compose up -d db
```

O volume persiste os dados entre reinicializações. A senha do `.env.example` é **somente para desenvolvimento local**.
Não publicar o `.env` e nunca enviar chaves por mensagens.

## 3. Testes

```bash
python3 scripts/validate_seed.py
source backend/.venv/bin/activate
PYTHONPATH=backend pytest -q backend/tests
```

## 4. Git

```bash
git init -b main
git add .
git commit -m "chore: estrutura inicial do SingMatch"
```

Criar repositório vazio no GitHub (sem README e sem .gitignore adicionais) e depois:

```bash
git remote add origin git@github.com:SEU_USUARIO/singmatch.git
git push -u origin main
```

Se já houver um repositório do projeto, verifique seu conteúdo antes de copiar arquivos, para não sobrescrever trabalho.

## 5. Divisão inicial

| Frente | Responsabilidade |
|---|---|
| A | `data/` + `scripts/import_catalog.py` |
| B | `backend/app/schemas.py` + `backend/app/llm.py` |
| C | `backend/app/{database,models,main,matching,catalog}.py` + deploy |
| D | `frontend/src/` + `frontend/vite.config.ts` |

O primeiro acordo coletivo deve ser o contrato Pydantic (arquivo `schemas.py`).
Depois integrar incrementalmente, sem esperar que cada parte esteja pronta.
