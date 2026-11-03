# Próximos passos após o scaffold

## Etapa 2 — Contratos (decidir em equipe)

- `ProfileDraft`: preferências, vetos com evidência, ambiguidade e consentimento de dueto.
- `ProfileConfirmed`: perfil revisado pela própria pessoa.
- `Song`: identidade, gênero e tags com fonte; dados ausentes não devem ser inferidos.
- `KaraokeVersion`: vídeo, duração, status e data da validação.
- `ScriptItem`: `karaoke_version_id`, lista de `participant_ids` (1 ou 2), posição e justificativa.
- `Script`: versão, revisão da sessão, items, aprovado.

## Etapa 3 — Banco e importador

Criar migração inicial versionada para `songs`, `karaoke_versions`, `sessions`, `participants`, `scripts`.
Não fazer `create_all` em produção. Importação UFMG/BYRM só após inspecionar cabeçalhos, encoding,
licença e identidade das gravações. Não mesclar linhas somente pelo título da música.

## Etapa 4 — Duas chamadas IA

Usar SDK OpenAI em `llm.py` com Structured Outputs. Primeiro interpretar; segundo compor roteiro
somente com IDs permitidos. Validar vetos/IDs no código. Não expor OPENAI_API_KEY ao frontend.
