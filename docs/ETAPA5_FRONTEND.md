# SingMatch — Etapa 5: React conectado à API

## O que há nesta entrega

Interface **real**, não simulada, com a identidade visual vinho/creme do PF2:

- organizador cria sala e copia código;
- participantes entram com código, escrevem preferências, recebem interpretação real do GPT e revisam as labels;
- confirmações são persistidas na API;
- organizador acompanha participantes, gera roteiro com GPT, troca músicas, reordena e aprova;
- participantes acompanham o roteiro sem visualizar textos privados uns dos outros;
- o organizador pode incorporar os vídeos do YouTube **somente após aprovar** o roteiro (player básico; controles/robustez podem ser ampliados na etapa 6);
- atualização da sala a cada 7 segundos, sem WebSocket;
- credenciais de sala por papel ficam em `sessionStorage` (separadas por aba e preservadas ao recarregar a mesma aba).

**Limitação intencional:** a API da Etapa 4 exige **uma apresentação solo para cada participante**; retirar uma pessoa do roteiro não é válido. O organizador pode trocar a música e alterar a ordem. Tentativas de usar vídeo vetado são rejeitadas pelo servidor com erro explicativo.

## Aplicação segura do ZIP

Na raiz do repositório:

```bash
cd ~/Downloads/SingMatch
git status
unzip -l ~/Downloads/singmatch_etapa5_frontend.zip
unzip -o ~/Downloads/singmatch_etapa5_frontend.zip -d .
```

Este pacote altera apenas `frontend/index.html`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/style.css` e adiciona `docs/ETAPA5_FRONTEND.md`. Não substitui código do backend, nem `.env`/`compose.yaml`.

## Rodar em desenvolvimento (dois terminais)

**Terminal 1 — API**: primeiro, certifique-se de que PostgreSQL está `healthy` e o backend tem as variáveis `DATABASE_URL`, `OPENAI_API_KEY` e `OPENAI_MODEL=gpt-5-mini` no ambiente do processo servidor. Se a API já está funcionando, pode mantê-la aberta.

```bash
cd ~/Downloads/SingMatch
source backend/.venv/bin/activate
set -a; source .env; set +a
# Se OPENAI_API_KEY está vazia no .env, configure sua chave neste terminal
# com o comando read, sem imprimi-la, ANTES de iniciar o Uvicorn.
python3 -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

**Terminal 2 — Vite**:

```bash
cd ~/Downloads/SingMatch/frontend
npm install
npm run dev
```

Acesse **http://127.0.0.1:5173/**. O Vite envia `/api` ao backend na porta 8000, por proxy já existente no projeto.

**O `npm install` precisa de internet na primeira execução.** Caso apareça erro de Node, confira `node --version` e `npm --version` (recomenda-se Node compatível com Vite 7, geralmente Node 20.19+ ou 22.12+).

### Teste guiado no navegador

1. Aba 1: `http://127.0.0.1:5173/` → **Criar sala** → copie o código.
2. Abra **nova aba normal** (não use “Duplicar aba”, que pode copiar a sessão). Clique **Entrar com código**, informe nome e código.
3. Na aba do participante, escreva o texto, clique **Interpretar com IA**, revise `likes`/`vetoes`, confirme. Observe o estado mudar na aba do organizador (até 7 s).
4. Abra outras duas abas novas para entrar como participantes diferentes e confirme os perfis (preferencialmente usando textos sem vetos incompatíveis).
5. Na aba organizador, **Gerar roteiro com IA** → **Editar roteiro** → trocar música ou mover → **Salvar alterações** → **Aprovar roteiro**.
6. Clique **Abrir o player**. O vídeo do YouTube só é incorporado na aba organizador; teste **Próxima apresentação**.
7. Recarregue a aba e confirme se a sessão é recuperada; faça uma alteração de perfil para verificar invalidação da aprovação e versão.

**Atenção às abas:** `sessionStorage` é separado por abas novas; ao **duplicar** uma aba, alguns navegadores clonam os dados da sessão, impedindo a entrada como outro papel. Uma janela anônima é alternativa. A opção “Sair deste dispositivo” descarta o token guardado, sem recuperação automática.

## Build e servir pela própria API

```bash
cd ~/Downloads/SingMatch/frontend
npm run build
```

Com o FastAPI rodando a partir do repositório, o código existente em `backend/app/main.py` encontra `frontend/dist` e serve o build em `http://127.0.0.1:8000/` depois de **reiniciar o servidor**. `GET /api/*` continua encaminhado à API.

Atenção: o `StaticFiles(html=True)` atual **não implementa fallback** para URLs arbitrárias da SPA. Essa versão não precisa de rotas React no caminho, pois usa uma única página.

## Segurança e limitações

- Tokens individuais são salvos em `sessionStorage`, nunca em repositório ou URL. Sair remove o token; manter a mesma aba permite atualizar e voltar.
- O código da sala não dá privilégios de organizador ou de outro participante.
- O frontend não aplica os vetos por conta própria: a API valida com o catálogo e os perfis confirmados. Se a música for proibida, aparecerá um erro do servidor.
- Os perfis devem ser revisados antes de serem confirmados; prompts podem conter dados pessoais: use textos fictícios no teste.
- O iframe não garante reprodução atual: YouTube pode remover/bloquear um vídeo. Link externo de fallback incluído. Verificar disponibilidade e direitos antes da apresentação pública.
- A UI não inclui um mecanismo de recuperação de tokens, exclusão de participantes, duetos, limite de pessoas, rate limiting, expiração de credenciais ou deploy público. Não compartilhe esta aplicação publicamente sem HTTPS e revisão de segurança.
- O estado de reprodução (qual vídeo está ativo) é **local** ao dispositivo do host e não fica sincronizado no banco. Só o roteiro e a aprovação são persistidos.

## Caso surja erro

- `Failed to fetch`/`API indisponível`: confira Uvicorn na porta 8000 e Vite na 5173.
- `403`: o token não corresponde ao participante/sala, ou a chave não tem acesso ao modelo.
- `409`: houve mudança de perfis, alteração de versão, veto ou ausência de solução. Atualize sala, ajuste perfis ou escolha outras músicas.
- `502`: a chamada ao GPT falhou; veja logs do backend, **sem copiar credenciais**.
