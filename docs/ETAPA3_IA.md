# SingMatch — Etapa 3: duas chamadas ao GPT

**Status:** implementação de prova de conceito, não é um endpoint publicado.

## Contratos

- `interpretar_perfil(text, songs)` → `ProfileDraft` (rascunho; o usuário deve confirmar).
- `compor_roteiro_solo(genre, intention, profiles_confirmed, songs, karaoke_versions)` → `ScriptProposal` (rascunho editável, NÃO aprovado).
- O GPT devolve JSON conforme esquema intermediário simples. O backend converte para os modelos `schemas.py` e reaplica validações locais.
- Cada preferência/veto possui evidência literalmente presente no texto; `duet_allowed=None` quando não informado.
- Apenas versões aprovadas do gênero são candidatas. Vetos confirmados são filtros obrigatórios, nunca apenas instruções ao GPT.
- No MVP são permitidas somente apresentações solo: exatamente uma por participante e sem repetição de vídeos.
- IDs inexistentes, vetos violados e duetos são rejeitados. Se não existe solução, **não** inventar roteiro.

## Executar na raiz do seu repositório

```bash
source backend/.venv/bin/activate
python3 -m pip install -U 'openai>=2,<3'  # atualização do SDK, se necessário
PYTHONPATH=backend python3 -m pytest -q backend/tests
PYTHONPATH=backend python3 scripts/demo_llm.py --modo contrato
```

Para as chamadas reais, exporte `OPENAI_API_KEY` localmente. Opcionalmente defina `OPENAI_MODEL` (o padrão do script é `gpt-4o-mini`). **Não comite `.env` nem o resultado contendo textos pessoais.**

```bash
read -srp 'Chave OpenAI: ' OPENAI_API_KEY; echo; export OPENAI_API_KEY
PYTHONPATH=backend python3 scripts/demo_llm.py --modo real
unset OPENAI_API_KEY
```

No modo real são feitas **duas chamadas à API**: uma interpreta o texto de P1; depois da confirmação no terminal, a segunda propõe um roteiro com P1, P2 e P3 (P2/P3 são exemplos previamente confirmados apenas para o ensaio).

## Limitacões / próximos passos

- Testes offline usam uma **API falsa** para provar validações; não medem a precisão do GPT.
- No MVP atual a função que bloqueia tags desconhecidas é conservadora. Mantenha a revisão das labels antes de expandir o catálogo.
- Não há edição, persistência, transações de revisão, autenticação nem endpoints nesta etapa. Integração com as rotas `/api` vem depois.
- Quando o usuário corrigir perfil, é necessário invalidar roteiros anteriores via `sessions.revision`.
- Se o modelo falhar ou gerar ID inválido, retorna erro sem apagar o último roteiro válido. Futuramente pode-se permitir **uma** tentativa de reparo.
- O Jev foi retirado do prazo de 7 dias: ambas as tarefas do MVP usam o SDK OpenAI.
