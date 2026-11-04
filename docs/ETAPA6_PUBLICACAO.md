# Etapa 6 — Publicação do SingMatch (piloto de 7 dias)

## Arquivos deste patch

- `Dockerfile`: gera o build do React e serve React + API no mesmo processo FastAPI.
- `.dockerignore`: exclui credenciais, repositório git e resultados privados do build.
- `backend/app/database.py`: aceita URL `postgresql://...` do Render e a converte internamente para `postgresql+psycopg://...`.
- `backend/migrations/env.py`: aplica a mesma normalização no Alembic.

O pacote **não altera** a IA, o frontend existente, os schemas, a curadoria nem os dados do usuário.

## 1. Aplicar no Ubuntu

```bash
cd ~/Downloads/SingMatch
git status
unzip -o ~/Downloads/singmatch_etapa6_publicacao.zip -d .
source backend/.venv/bin/activate
PYTHONPATH=backend python3 -m pytest -q backend/tests
PYTHONPATH=backend python3 - <<'PY'
from app.database import normalize_database_url
assert normalize_database_url('postgresql://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
assert normalize_database_url('postgresql+psycopg://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
print('OK: URL PostgreSQL normalizada.')
PY
```


## 2. Build Docker local (opcional, recomendado)

```bash
docker build -t singmatch:deploy .
```

No Ubuntu, para testar em container utilizando seu PostgreSQL local via host network, pare o Uvicorn que já usa a porta 8000 e execute:

```bash
docker run --rm --network host --env-file .env -e PORT=8000 singmatch:deploy
```

A aplicação deve abrir em `http://127.0.0.1:8000/`, e o healthcheck em `/api/health`. Se `.env` tiver `OPENAI_API_KEY=` vazia, a IA não responderá neste teste em container; isso não impede verificar página, API e banco.

## 3. GitHub

Confirme primeiro que `.env` está ignorado: `git check-ignore .env`.

```bash
git add Dockerfile .dockerignore backend/app/database.py backend/migrations/env.py docs/ETAPA6_PUBLICACAO.md
git diff --cached --stat
git commit -m "chore: preparar deploy unificado React FastAPI"
git push
```

## 4. Render: banco e serviço

1. Em https://dashboard.render.com/, crie um **Postgres** (para demonstração pode ser Free, com prazo de 30 dias e sem backups; não use para armazenar dados valiosos).
2. Crie um **Web Service** a partir do repositório GitHub atualizado. Na opção de linguagem/runtime selecione **Docker**, com Dockerfile na raiz do repositório. Escolha a mesma região do banco.
3. Em **Environment** do Web Service, configure:
   - `DATABASE_URL`: **Internal Database URL** do PostgreSQL Render (não a URL local `localhost`), armazenada como variável secreta.
   - `OPENAI_API_KEY`: chave de projeto autorizada (nunca no GitHub).
   - `OPENAI_MODEL`: `gpt-5-mini` (modelo validado antes; sujeito a permissões/créditos).
4. Inicie o deploy e acompanhe o log. O comando inicial roda `alembic upgrade head`, importa as cinco músicas sem duplicar e inicia o Uvicorn ouvindo em `0.0.0.0:$PORT`.
5. Acesse `https://<seu-servico>.onrender.com/api/health`, depois `/api/catalog` e `/`.
6. Teste primeiro com dados fictícios em aparelhos/abas distintos; teste vídeos do YouTube no domínio real.

**Atenção:** no plano Free, o PostgreSQL Render expira em 30 dias, não oferece backups e o Web Service pode ficar inativo após períodos sem acesso. Faça exportação de dados de teste ou considere um banco pago/persistente se necessário depois do checkpoint.

## 5. Segurança antes de divulgar o link

- Este backend ainda não implementa limite de requisições nem cota de chamadas OpenAI por sala. **Não divulgue amplamente o URL com uma chave institucional** antes de limitar o consumo na plataforma e implementar rate limiting.
- Compartilhe a versão de demonstração inicialmente só com o grupo e avaliadores conhecidos; monitore os logs e o uso de API.
- Use dados fictícios nos testes. O frontend guarda credenciais da sessão na aba do navegador; não crie salas com informações sensíveis.
- A curadoria aprovada dos cinco vídeos não é garantia de que ainda permitam incorporação ou de direitos autorais; revise no domínio publicado.
