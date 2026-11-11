# SingMatch 🎤

**Karaokê coletivo organizado com inteligência artificial.** O SingMatch permite criar uma sala, reunir participantes, interpretar preferências musicais escritas em linguagem natural e propor um roteiro personalizado de apresentações. O organizador pode revisar, editar e aprovar o roteiro antes de reproduzir as músicas.

Projeto acadêmico desenvolvido para a disciplina de **Criatividade Computacional**.

> **Escopo desta versão (MVP):** músicas de **forró**, uma apresentação **solo por participante** e reprodução no dispositivo do organizador. **Duetos inteligentes e novos gêneros** são evoluções planejadas, não funcionalidades deste PR.

## Funcionalidades

- **Salas compartilhadas:** o organizador cria uma sala com uma intenção musical; os participantes entram usando um código.
- **Preferências em texto livre:** cada participante informa gostos e restrições. A IA sugere um perfil estruturado com preferências positivas (*likes*), vetos e eventuais perguntas de esclarecimento.
- **Confirmação humana:** cada participante revisa e confirma o próprio perfil antes de o roteiro ser gerado.
- **Roteiro com IA:** a composição considera as preferências individuais, os vetos, a intenção da noite e a progressão musical.
- **Diversidade entre gerações:** ao gerar outra proposta, o sistema utiliza o histórico do roteiro anterior da sala para favorecer alternativas quando possível.
- **Afinidade individual:** o modelo recebe pontuações de compatibilidade calculadas a partir das preferências de cada pessoa.
- **Regras verificadas no backend:** apenas vídeos elegíveis; uma apresentação solo por pessoa; sem repetir vídeo ou participante na mesma rodada; vetos não podem ser violados.
- **Revisão pelo organizador:** é possível gerar novamente, trocar músicas, reorganizar apresentações, editar o título e aprovar a versão final.
- **Reprodução de karaokê:** o player fica disponível no dispositivo do organizador após a aprovação.

**Importante:** a interpretação da IA gera um *rascunho*, e o roteiro gerado é uma *proposta*. Nenhum deles é confirmado automaticamente em nome dos usuários.

## Catálogo e curadoria

O catálogo atual está fechado para este MVP:

| Indicador | Quantidade |
| --- | ---: |
| Músicas de forró cadastradas | **161** |
| Karaokês aprovados para o MVP | **98** |
| Músicas do piloto inicial | 5 |
| Músicas do catálogo ampliado | 156 |

Os 98 vídeos de karaokê foram revisados para uso no piloto. Os roteiros desta versão devem utilizar **somente versões do tipo `karaoke` aprovadas**; versões de músicas originais com letra sincronizada não fazem parte das escolhas do roteiro.

Arquivos relevantes:

- `data/catalogo_piloto.json`: cinco músicas do piloto inicial.
- `data/catalogo_forro.json`: catálogo ampliado e versões de vídeo.
- `data/fontes/auditoria_karaoke.csv`: registro da auditoria manual.
- `data/fontes/videos_verificados.json`: histórico de verificações de reprodução.
- `data/fontes/karaokes_curados.json`: escolhas de karaokê incorporadas à curadoria.
- `data/fontes/karaokes_rejeitados.json`: vídeos descartados após revisão.
- `scripts/import_catalog.py`: importação das músicas e versões para o PostgreSQL.

> **Limitações:** a disponibilidade e a incorporação dos vídeos do YouTube podem mudar. Aprovação na auditoria técnica **não equivale à autorização de uso ou revisão de direitos autorais**. Os metadados musicais também podem exigir revisão humana contínua.

## Tecnologias

| Camada | Tecnologias |
| --- | --- |
| Frontend | React, TypeScript e Vite |
| Backend | Python 3.12, FastAPI, Pydantic e SQLAlchemy |
| Banco de dados | PostgreSQL 16 e Alembic |
| IA | OpenAI API, Responses e Structured Outputs |
| Reprodução | Player com vídeos incorporados do YouTube |
| Infraestrutura | Docker / Docker Compose e Render |
| Testes | Pytest; TypeScript e build do Vite |

## Estrutura do projeto

```text
SingMatch/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI e montagem do frontend compilado
│   │   ├── routes.py          # Endpoints: salas, perfis, roteiro e aprovação
│   │   ├── llm.py             # Interpretação de preferências e composição com IA
│   │   ├── matching.py        # Elegibilidade, afinidade e regras do roteiro
│   │   ├── catalog.py         # Leitura do catálogo no banco
│   │   ├── schemas.py         # Contratos Pydantic
│   │   └── database.py        # Configuração das sessões de banco
│   ├── migrations/            # Migrações Alembic
│   └── tests/                 # Testes do backend
├── frontend/
│   └── src/                   # Interface React e player
├── data/
│   ├── catalogo_piloto.json
│   ├── catalogo_forro.json
│   └── fontes/                # Fontes, verificações e curadoria
├── scripts/
│   ├── import_catalog.py
│   ├── validate_seed.py
│   ├── avaliar_perfis.py
│   ├── avaliar_roteiros.py
│   └── avaliar_fluxo_integrado.py
├── compose.yaml              # PostgreSQL local
├── Dockerfile                 # Build e execução para deploy
└── .env.example               # Exemplo de configuração; sem credenciais reais
```

## Executar localmente

### Pré-requisitos

- Python **3.12** recomendado, com `venv` e `pip`;
- Node.js compatível com Vite 7 (**20.19+** ou **22.12+**) e npm;
- Docker com Docker Compose;
- chave da OpenAI API para interpretar perfis e gerar roteiros reais.

Os comandos a seguir devem ser executados na **raiz do repositório**, salvo quando indicado.

### 1. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite `.env` e configure, no mínimo:

```dotenv
# Exemplo EXCLUSIVAMENTE local: use a mesma senha na URL e no Compose.
POSTGRES_DB=singmatch
POSTGRES_USER=singmatch
POSTGRES_PASSWORD=dev-local-change-me
DATABASE_URL=postgresql+psycopg://singmatch:dev-local-change-me@127.0.0.1:5432/singmatch

# Configure sua chave local; nunca a envie ao Git.
OPENAI_API_KEY=
# Escolha um modelo ao qual sua conta tenha acesso.
OPENAI_MODEL=gpt-4o-2024-05-13
```

Os valores acima são **exemplos de desenvolvimento**. Use credenciais adequadas ao seu ambiente. Se um volume PostgreSQL já existir, alterar a senha no `.env` não atualiza automaticamente a senha gravada no banco.

**Nunca versione `.env`, tokens ou resultados contendo informações privadas dos participantes.**

### 2. Subir o PostgreSQL

```bash
docker compose up -d db
docker compose ps
```

O banco do Compose é publicado apenas em `127.0.0.1:5432`.

### 3. Criar ambiente Python e instalar dependências

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
```

### 4. Criar tabelas e importar o catálogo

**Atenção: os comandos abaixo modificam o banco definido em `DATABASE_URL`.** Antes de executá-los, confirme que o host é local:

```bash
python - <<'PY'
from dotenv import dotenv_values
from urllib.parse import urlsplit

url = dotenv_values('.env').get('DATABASE_URL', '')
host = urlsplit(url).hostname if url else None
print('Host do banco:', host)
if host not in {'127.0.0.1', 'localhost', '::1'}:
    raise SystemExit('Não executar migração/importação: banco não é local.')
PY
```

Carregue a URL local na sessão do terminal e execute as migrações:

```bash
export DATABASE_URL="$(python -c 'from dotenv import dotenv_values; print(dotenv_values(".env")["DATABASE_URL"])')"
python -m alembic -c backend/alembic.ini upgrade head
python scripts/import_catalog.py
```

### 5. Iniciar a API

```bash
python -m uvicorn app.main:app \
  --app-dir backend \
  --env-file .env \
  --reload \
  --host 127.0.0.1 \
  --port 8000
```

Mantenha esse terminal aberto. Verifique:

- API: <http://127.0.0.1:8000/api/health>
- Catálogo: <http://127.0.0.1:8000/api/catalog?genre=forro>
- Documentação interativa: <http://127.0.0.1:8000/docs>

### 6. Iniciar o frontend

Em **outro terminal**:

```bash
cd frontend
npm ci
npm run dev
```

Abra <http://127.0.0.1:5173>. Durante o desenvolvimento, o Vite encaminha as requisições `/api` para o FastAPI na porta 8000.

## Como utilizar

1. O **organizador** cria uma sala de forró e informa a intenção da noite (por exemplo: “começar tranquilo e terminar animado”).
2. Compartilha o **código da sala** com os participantes.
3. Cada participante entra na sala, escreve suas preferências e solicita a **interpretação pela IA**.
4. Cada pessoa **revisa e confirma** seu perfil.
5. O organizador solicita a **geração de roteiro** e pode gerar outra proposta, editar a ordem e substituir músicas.
6. O organizador **aprova** o roteiro e abre o player no próprio dispositivo.

Para simular participantes no mesmo computador, use sessões independentes do navegador, de modo que os tokens de acesso não se confundam.

## API — principais endpoints

| Método | Rota | Finalidade |
| --- | --- | --- |
| `GET` | `/api/health` | Estado da API |
| `GET` | `/api/catalog?genre=forro` | Catálogo disponível |
| `POST` | `/api/sessions` | Criar sala |
| `POST` | `/api/join` | Entrar com código |
| `GET` | `/api/sessions/{session_id}` | Consultar sala e roteiro |
| `POST` | `/api/participants/{participant_id}/interpret` | Interpretar preferências com IA |
| `PUT` | `/api/participants/{participant_id}/profile` | Confirmar/corrigir perfil |
| `POST` | `/api/sessions/{session_id}/script` | Gerar proposta com IA |
| `PUT` | `/api/sessions/{session_id}/script` | Editar proposta |
| `POST` | `/api/sessions/{session_id}/script/approve` | Aprovar roteiro |

A API utiliza **tokens Bearer por papel**: o participante controla o próprio perfil, enquanto o organizador controla o roteiro. Consulte `/docs` para os formatos completos das requisições e respostas.

## Testes e avaliações

### Testes automatizados

A partir da raiz, com o ambiente virtual ativado:

```bash
python scripts/validate_seed.py
PYTHONPATH=.:backend python -m pytest -q backend/tests
```

Build de produção do frontend:

```bash
cd frontend
npm ci
npm run build
```

**Última validação local informada pela equipe:** 62 testes do backend aprovados, build do frontend bem-sucedido, 161 músicas no PostgreSQL local, 98 karaokês aprovados e nenhum dos dois vídeos rejeitados mantido como aprovado.

### Avaliações experimentais da IA

Os scripts abaixo utilizam **perfis fictícios** e não modificam o banco. O modo `contrato` verifica a preparação dos casos sem consumir API; o modo `real` faz chamadas à OpenAI e pode gerar custos.

```bash
# Interpretação de preferências
PYTHONPATH=.:backend python scripts/avaliar_perfis.py --modo contrato --cenario todos
PYTHONPATH=.:backend python scripts/avaliar_perfis.py --modo real --cenario simples --limite 3

# Diversidade de roteiros
PYTHONPATH=.:backend python scripts/avaliar_roteiros.py --modo contrato --cenario todos
PYTHONPATH=.:backend python scripts/avaliar_roteiros.py --modo real --cenario iguais --repeticoes 2

# Interpretação de perfis + composição em sequência
PYTHONPATH=.:backend python scripts/avaliar_fluxo_integrado.py --modo contrato
PYTHONPATH=.:backend python scripts/avaliar_fluxo_integrado.py --modo real --geracoes 2
```

Resultados observados nas avaliações controladas realizadas durante o desenvolvimento:

- **Perfis:** 20 de 20 cenários de teste aprovados após ajuste do prompt, incluindo preferências combinadas, formatos e ambiguidades.
- **Diversidade:** repetição agregada de **58,3% sem histórico** contra **0% com histórico**, em quatro cenários de comparação com três músicas cada.
- **Fluxo integrado:** dois roteiros consecutivos com **100% de afinidade das labels positivas**, **0% de repetição entre roteiros**, nenhum veto violado e energia não decrescente.

Esses números descrevem **amostras pequenas e cenários fictícios**: são evidências experimentais, não garantia de desempenho universal ou avaliação estatística conclusiva. As chamadas reais dependem da chave e do modelo configurados.

Os relatórios de execução podem ser gravados em `resultados/`. Revise seu conteúdo antes de compartilhá-los ou versioná-los.

## Publicação no Render

O `Dockerfile` constrói o frontend e executa FastAPI e React na mesma origem. Na inicialização do contêiner, ocorre esta sequência:

1. `alembic -c backend/alembic.ini upgrade head`;
2. `python3 scripts/import_catalog.py`;
3. inicialização do Uvicorn.

**Não faça merge/deploy automaticamente ao abrir um PR.** Antes de publicar alterações do catálogo, confirme as variáveis de ambiente do Render, faça backup do PostgreSQL de produção, revise as mudanças na importação e confira as aprovações já existentes. Não inclua credenciais no Dockerfile ou no repositório.

A versão pública pode estar diferente da branch em desenvolvimento até a conclusão do merge e do deploy.

## Próximas etapas

**Após a integração deste MVP:**

- Ampliar os gêneros musicais, com curadoria e validação de novos karaokês.
- Implementar **duetos inteligentes** com consentimento dos participantes e regras próprias de formação de pares.
- Permitir roteiros mistos (apresentações solo e duetos).
- Refinar a experiência de uso, a observabilidade e os testes com usuários reais.

Esses recursos **não fazem parte do escopo atual** e devem ser desenvolvidos e validados separadamente.

## Contribuição e cuidados

- Desenvolva novas funcionalidades em **branches** e proponha alterações por **Pull Request**.
- Rode os testes e o build antes de abrir um PR.
- Não use `git add .` sem revisar arquivos de teste gerados, relatórios, CSVs temporários e credenciais.
- Não publique textos reais de preferências ou tokens de participantes.
- Valide mudanças no catálogo em um **banco local** antes de qualquer migração/importação em produção.

---

**SingMatch — Criatividade Computacional:** IA para transformar preferências individuais em uma experiência musical coletiva.