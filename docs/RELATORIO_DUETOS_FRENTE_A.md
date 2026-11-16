# Frente A — Duetos: regras e comparação

## Regras de matching implementadas

- Consentimento para dueto é explícito: `duet_allowed` precisa ser `true` nos dois perfis. `false` e `null` não autorizam duetos; não impedem solos.
- Compatibilidade de par exige ao menos uma obra marcada `duet_possible`, com versão aprovada, que não viole vetos de nenhum dos participantes. Vetos de formato (ex.: "não quero dueto") não são interpretados como veto musical.
- A elegibilidade musical individual continua aplicando as regras existentes, incluindo *fail closed* para tags sem metadados suficientes.
- Cada participante deve aparecer exatamente uma vez no roteiro, solo ou numa dupla. Um vídeo não pode se repetir; a dupla precisa estar autorizada e a música precisa admitir dueto. Validação backend não depende do prompt.
- Fallback: composição mista recebe candidatos solo permitidos e duplas elegíveis. Sem par compatível, solos permanecem disponíveis; se o modelo tentar duetos não autorizados, a proposta é rejeitada.

## Afinidade, diversidade e equilíbrio

- `duet_affinity` mede 0–1 pela proporção de obras duetáveis que correspondem a gostos explicitamente declarados por ambos. Não infere gosto ausente; retorna 0 quando não há dados comparáveis.
- Diversidade: o contrato `ScriptProposal` impede repetição de versões/vídeos; validação mista limita os itens a solos/duetos e a cobertura de participantes sem repetição.
- Equilíbrio: cada pessoa aparece exatamente uma vez na rodada (solo ou dueto), portanto a contagem individual é uniforme.

## Comparação funcional com o fluxo exclusivamente solo

| Critério | Solo anterior | Matching misto Frente A |
|---|---|---|
| Consentimento | Não aplicável; todos solo | Exigido de ambos, explicitamente |
| Veto musical | Validado individualmente | Validado individualmente para ambos na obra do dueto |
| Formação de par | Não existia | Exige obra aprovada duetável e interseção das obras compatíveis |
| Fallback solo | Só solos | Mantém solos quando duetos não são possíveis |
| Cobertura/justiça | Uma aparição por pessoa | Uma aparição por pessoa, não importa formato |
| Diversidade | Sem repetir vídeo | Sem repetir vídeo, pela validação existente do contrato |
| Afinidade | Likes ranqueiam candidatas solo | Score de gostos compartilhados disponibilizado à composição |

Esta comparação é de regras/contratos; não afirma melhora empírica de satisfação ou qualidade. A validação offline com clientes simulados não mede a qualidade de saídas reais do modelo. A função de composição mista foi adicionada para uso pela integração; rotas, interface e player ficam fora da Frente A.