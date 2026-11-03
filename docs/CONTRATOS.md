# SingMatch — Contratos do MVP (etapa 2)

Esses contratos estão em `backend/app/schemas.py` (Pydantic 2) e são a referência compartilhada para as quatro frentes.

## 1. Catálogo
- `Song`: identidade e metadados da *obra*, inclusive `genre`, `energy` (opcional 1–5), `mood` e `tags` com `attribute/value/source`.
- `KaraokeVersion`: identifica o *vídeo* de karaokê por ID do YouTube, com `approved`, `verified_at` e `duration_seconds` independentes da gravação original.
- Não supor colunas específicas do Zenodo nem converter tags sem documentação.
- `duet_possible=True` significa **pode ser solo ou dueto**; `False` significa não oferecer essa música em dueto.

## 2. Interpretação do texto (IA 1)
- Entrada `InterpretRequest`: `{"text": "Gosto de forró, mas não de músicas românticas"}`.
- Saída `ProfileDraft`: `likes`, `vetoes`, `preferred_format`, `duet_allowed`, `questions`.
- Cada preferência possui `category` (`genre|artist|song|tag`), `value`, `evidence` e `origin`.
- Exemplo: `{"category":"tag","value":"romantica","evidence":"não de músicas românticas","origin":"texto"}` é veto.
- Sem opinião explícita sobre dueto, `duet_allowed` deve ser `null`, não `true`.
- O próprio participante corrige e confirma o perfil (`ConfirmProfileRequest`). Uma resposta estruturada não garante interpretação semanticamente correta.

## 3. Composição de roteiro (IA 2)
- `ScriptProposal`: `title` + `items` com `position`, `karaoke_version_id`, `participant_ids`, `justification`, `origin`.
- Na primeira versão, usar **somente solo**: cada item contém exatamente 1 `participant_id`. Pydantic suporta 2 para quando o grupo habilitar duetos.
- O esquema rejeita IDs de participantes repetidos, versões de karaokê repetidas e posições duplicadas/descontínuas.
- **Não valida a existência de IDs no banco** nem disponibilidade de cada música, nem veto, nem consentimento. Essas regras pertencem a `matching.py`.
- Em qualquer alteração, enviar `expected_version`. O backend compara com a versão do banco para evitar sobrescrita.
- Mudança de perfil deve incrementar `session.revision` e invalidar aprovação de roteiro antigo.

## 4. Sessões, acesso e segurança
- `CreateSessionResponse` contém `host_token`; `SessionPublic` não contém token.
- `JoinSessionResponse` retorna `participant_token` somente ao dono daquele participante.
- O código da sala não concede poderes de organizador nem de editar perfis de outras pessoas.
- Não guardar token em texto puro no PostgreSQL. No banco, armazenar hashes.
- Não colocar o token em URLs públicas nem em `GET /api/sessions/{id}`.

## 5. Responsabilidade por arquivo
- **A (dados):** fornecer `Song` e `KaraokeVersion`, preservar fonte e corrigir a importação.
- **B (IA):** gerar `ProfileDraft` e `ScriptProposal` via modelos; prompts versionados.
- **C (backend):** implementar modelos SQLAlchemy, tokens, rotas e regras além do schema.
- **D (frontend):** consumir respostas públicas da API e construir edição/aceitação.

## 6. Smoke test

```bash
source backend/.venv/bin/activate
PYTHONPATH=backend pytest -q backend/tests
```

No fim, `GET /api/health` continua respondendo como antes. A etapa 2 *ainda não implementa* as rotas de sessão, o banco ou chamadas reais de IA.
