# SingMatch — Etapa 4: API + banco (MVP solo)

## O que esta etapa entrega

- PostgreSQL + SQLAlchemy 2.0, tabelas **songs, karaoke_versions, sessions, participants, scripts**.
- Migração inicial **versionada** por Alembic (`backend/migrations/versions/0001_initial.py`).
- Catálogo inicial de **5 músicas / 5 versões de vídeo** (importação idempotente do JSON piloto).
- Tokens independentes (organizador e participante), com **somente hashes SHA-256 armazenados no banco**.
- Sala com código aleatório de 8 caracteres, sem cadastro permanente.
- Perfis interpretados por GPT e confirmados pela pessoa em rotas separadas.
- Roteiro solo persistido com versão, revisão de perfis e validação de vetos/IDs.
- Troca, remoção e reordenação via PUT do roteiro completo, com justificativas antigas invalidadas quando alteradas.
- Aprovação bloqueada se alguém entrou, corrigiu o perfil ou se o roteiro já foi atualizado.
- Estado consultável por token, sem dados privados de outros participantes.
- 23 testes automatizados **offline** (17 das etapas anteriores + 6 de integração).

**Não entrega nesta etapa:** formulários React de sala/participante, player funcional, duetos, sincronização em tempo real, deploy público, importação dos CSVs UFMG/BYRM. As duas tarefas de IA (`llm.py`) são reutilizadas sem alteração.

## Instalar a atualização

Aplique na raiz de seu repositório, somente após `git status` e comparar modificações concorrentes.

```bash
cd ~/Downloads/SingMatch
unzip -l ~/Downloads/singmatch_etapa4_api.zip
unzip -o ~/Downloads/singmatch_etapa4_api.zip -d .
source backend/.venv/bin/activate
python3 -m pip install -r backend/requirements.txt
PYTHONPATH=backend python3 -m pytest -q backend/tests
```

**Atenção:** este ZIP altera `backend/app/main.py`, `database.py`, `models.py`, `catalog.py`, `backend/requirements.txt` e `scripts/import_catalog.py`, e acrescenta novos arquivos. Não altera `schemas.py`, `llm.py`, `matching.py` nem os arquivos do frontend.

## Subir PostgreSQL (Ubuntu, Docker com Compose)

No diretório do projeto, se ainda não existir `.env`:

```bash
cp .env.example .env
```

Troque `POSTGRES_PASSWORD` e a senha correspondente na `DATABASE_URL` por uma **senha local própria** antes de criar o volume. Se já existir banco/volume, não troque a senha sem atualizar o banco também.

```bash
docker compose up -d db
docker compose ps
```

Carregue as variáveis do `.env` no shell atual:

```bash
set -a
source .env
set +a
```

Cuidado: um campo `OPENAI_API_KEY=` vazio em `.env` pode sobrescrever sua variável anterior. Se isso acontecer, configure sua chave novamente **depois** de carregar `.env` (não a cole na conversa, nos logs ou no GitHub).

Use o modelo já testado na organização da disciplina:

```bash
export OPENAI_MODEL=gpt-5-mini
```

Faça a migração e importe o piloto:

```bash
alembic -c backend/alembic.ini upgrade head
python3 scripts/import_catalog.py
```

Deve informar `5 músicas novas, 5 versões novas` na primeira execução e `0 novas` na segunda.

Inicie API:

```bash
python3 -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Abrir `http://127.0.0.1:8000/docs` para visualizar a documentação interativa, ou `http://127.0.0.1:8000/api/catalog` para conferir os cinco registros.

**Sem Docker:** use PostgreSQL já instalado e informe sua `DATABASE_URL` com `postgresql+psycopg://usuario:senha@host:5432/banco`. A migração é igual.

## Endpoints

| Método | Rota | Token necessário | Resposta principal |
|---|---|---|---|
| GET | `/api/health` | Não | `status=ok` |
| GET | `/api/catalog?genre=forro` | Não | músicas e vídeos aprovados |
| POST | `/api/sessions` | Não | `session`, `host_token` |
| POST | `/api/join` | Não (código de sala) | `participant_id`, `participant_token` |
| GET | `/api/sessions/{id}` | Host ou membro da sala | dados públicos e último roteiro |
| POST | `/api/participants/{id}/interpret` | Do próprio participante | `draft` da IA |
| GET | `/api/participants/{id}/profile` | Do próprio participante | texto + draft + confirmado |
| PUT | `/api/participants/{id}/profile` | Do próprio participante | perfil confirmado |
| POST | `/api/sessions/{id}/script` | Host | proposta gerada |
| PUT | `/api/sessions/{id}/script` | Host | nova versão editada |
| POST | `/api/sessions/{id}/script/approve` | Host | roteiro aprovado |

Cabeçalho: `Authorization: Bearer <token>` (exceto nas rotas públicas). O código de sala **não** autoriza modificação de perfis alheios.

### Pedidos de exemplo

Criar sala:

```http
POST /api/sessions
Content-Type: application/json

{"genre":"forro", "intention":"começa tranquilo e termina animado"}
```

Entrar:

```http
POST /api/join
Content-Type: application/json

{"code":"CODIGO_DA_SALA", "name":"Ana"}
```

Interpretar preferências (com o token do participante):

```http
POST /api/participants/ID_DA_PESSOA/interpret
Authorization: Bearer TOKEN_DA_PESSOA
Content-Type: application/json

{"text":"Gosto de forró animado, não gosto de músicas românticas e prefiro solo."}
```

Confirmar (enviar o rascunho revisado pelo usuário):

```http
PUT /api/participants/ID_DA_PESSOA/profile
Authorization: Bearer TOKEN_DA_PESSOA
Content-Type: application/json

{"profile": {"likes":[], "vetoes":[], "preferred_format":"solo", "duet_allowed":false, "questions":[]}}
```

Os `likes` e `vetoes` acima são **apenas um exemplo de formato**. A interface deve enviar o perfil efetivamente revisado, não apagar vetos silenciosamente.

Editar: `PUT /api/sessions/{id}/script` recebe
`{"expected_version": 1, "proposal": {"title":"...", "items":[...]}}`.
A edição deve enviar todos os participantes exatamente uma vez. Remover um item exige **substituir por outro válido** ou resolver a ausência de solução; não é possível terminar uma rodada omitindo uma pessoa.

Aprovar: `POST /api/sessions/{id}/script/approve` recebe `{"expected_version": 2}`.

## Testes rápidos

**Sem gastar API**:

```bash
PYTHONPATH=backend python3 -m pytest -q backend/tests
```

**Teste ponta a ponta real**, requer API rodando, banco e chave, e executa até **4 chamadas à OpenAI** com textos fictícios (pode ter custo):

```bash
python3 scripts/smoke_api.py --real
```

A demonstração confirma automaticamente os rascunhos **somente para teste**; na interface final o usuário deve revisar e confirmar explicitamente.

## Proteções e limitações

- Não use `.env` em Git; o `.gitignore` da Etapa 1 já o exclui.
- Não imprima `host_token`, `participant_token`, texto privado nem a chave da API em logs.
- Hash de token evita armazenamento de credenciais em claro; use **HTTPS** na publicação.
- Esta é autenticação mínima de demonstração: ainda faltam rate limiting, expiração/rotação de tokens, limites por sala, monitoramento e política de retenção dos textos.
- Banco de testes usa **SQLite**. PostgreSQL em Docker está configurado, mas a migração e o fluxo devem ser conferidos também no computador que executará a demonstração.
- Se o GPT falhar, a rota responde HTTP 502. O último roteiro persistido não é apagado.
- Se um participante mudar enquanto o GPT responde, retornamos HTTP 409 e descartamos a resposta antiga.
- `GET /api/sessions/{id}` omite preferências e textos privados; só o próprio participante pode ler o texto via rota privada.
- Versões de karaoke precisam de aprovação humana; IDs importados da curadoria piloto não garantem disponibilidade atual.
