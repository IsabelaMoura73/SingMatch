# Etapa 7: catálogo ampliado e vídeos de letra

Esta etapa resolve dois problemas para a apresentação: o catálogo tinha **5 músicas** e não havia
um jeito eficiente de obter vídeos com letra.

## Resumo

| Antes | Depois |
|---|---|
| 5 músicas com vídeo de karaokê achado à mão | 5 do piloto + 113 novas = **118 músicas** de forró |
| Cada vídeo novo exigia buscar e testar um karaokê no YouTube | `scripts/build_catalog.py` monta o catálogo sozinho a partir dos datasets |
| O player era um `<iframe>` simples | Player com a YouTube IFrame API: mostra a **letra sincronizada** abaixo do vídeo, com efeito de karaokê, ajuste de sincronia e tela cheia |

> **Karaokê × cante junto.** As 5 músicas do piloto são **karaokê** de verdade (vídeo instrumental com
> a letra embutida). As 113 novas são **cante junto**: a gravação original, **com a voz do cantor**, e a
> letra sincronizada desenhada pelo player. O player mostra o selo "Vídeo de karaokê" ou "Letra
> sincronizada · voz original". No banco, isso fica em `karaoke_versions.kind`.

## Como o "vídeo de letra" é gerado

Não renderizamos vídeo. O player toca a **gravação original** no YouTube e desenha a letra no tempo do
vídeo (`player.getCurrentTime()`), a partir de um arquivo **LRC** (`[mm:ss.xx] linha da letra`).

O ponto crítico é a sincronia. Ela só funciona se a letra foi marcada **na mesma gravação** do vídeo.
O script aceita uma letra apenas quando a duração do vídeo e a da letra diferem em até 3 s.

```
BYRM (ID do YouTube) ──┐
                       ├─► LRCLIB: letra sincronizada com a MESMA duração? ──► vídeo incorporável? ──► catálogo
UFMG (título/artista) ─┘        └─ não: busca no YouTube um upload oficial com essa duração ─┘
```

Tipos de versão (`karaoke_versions.kind`):

- `karaoke`: as 5 do piloto. O vídeo já traz a letra e o player só reproduz.
- `letra_sincronizada`: as novas. Vídeo original + LRC (`GET /api/karaoke_versions/{id}/lyrics`).

## Vídeo bloqueado fora do YouTube (erro 150)

Muitos uploads oficiais (gravadoras de Luiz Gonzaga, Dorgival Dantas e parte do Aviões do Forró) passam
nas checagens "estáticas" (oEmbed responde e a página diz `playableInEmbed`), mas o player incorporado
recusa com **erro 150** quando tenta tocar. Isso só se descobre tocando. Por isso:

1. `build_catalog.py` junta até 4 vídeos candidatos por música e grava os ainda não testados em
   `data/fontes/videos_a_verificar.txt`.
2. Abra **`/verificar.html?ids=<conteúdo do arquivo>`** no site (local ou publicado) e clique em
   *Verificar*. Cada vídeo toca **sem som** no player real e é marcado como ok ou bloqueado.
3. Copie o JSON do fim da página e rode `python3 scripts/registrar_verificacao.py resultado.json`
   (atualiza `data/fontes/videos_verificados.json`).
4. Rode `build_catalog.py` de novo: **só entra no catálogo vídeo que tocou** e, para música com vídeo
   bloqueado, o script tenta o próximo candidato.

`/verificar.html` sem parâmetros testa o catálogo inteiro que está no ar. **Rodar no domínio do Render
antes da apresentação.** O `import_catalog.py` usa a lista de bloqueados para revogar `approved` em
bancos já existentes e para trocar o vídeo do piloto quando o JSON traz um substituto verificado. Foi o
que aconteceu com `KAR-FOR-004` (O Xote das Meninas): o karaokê de 29/10 (`ZFGBYMnc-MU`) passou a
dar erro 150 e foi trocado por `Kw7IgoDs1NE`.

## O que encontramos nos datasets

**BYRM (Zenodo 16617888, UFAM, CC BY 4.0).** É o mais útil. O metadado de forró tem 106 faixas com
**ID do vídeo do YouTube**, título e canal. Não tem letra nem gênero detalhado. Os nomes misturam
"Artista - Título", "Título - Artista" e canais "Artista - Topic"; o script separa título e artista e
`data/fontes/ajustes_byrm.json` corrige os casos ambíguos.

**UFMG (Zenodo 12733931, CC BY 4.0).** `treino_avaliacao.csv` tem 73.687 músicas, das quais 2.702
estão rotuladas como "forró". O rótulo **não é confiável**: a lista inclui Xuxa (422), Lulu Santos (206),
Anitta, Shakira e Madonna. O único artista de forró de fato é **Aviões do Forró (514 músicas)**, e só
esse entra (`UFMG_FORRO_ARTISTS` no script). A letra vem pré-processada (minúsculas, lematizada) e
não serve para exibir. As emoções (raiva, medo, alegria, tristeza, surpresa) viram a tag
`emocao_letra`, sem conversão para clima. Elas parecem **pouco confiáveis**: "Festa na Piscina" e
"Jeito Carinhoso" saem com *raiva* dominante. Por isso o matching não depende delas (só contam como
preferência positiva) e clima e energia vêm da curadoria. `data/fontes/ufmg_forro.csv` guarda só as colunas usadas
(sem letra).

**Pesquisa por vertente (`data/fontes/pesquisa_forro.csv`).** Os datasets cobrem pouco do que se
canta numa festa em Recife (BYRM tem só 106 faixas e a UFMG só traz Aviões do Forró de verdade). Por
isso montamos uma terceira lista com pesquisa assistida por IA em três frentes: clássicos/pé de serra,
forró universitário/MPB nordestina e forró eletrônico/piseiro. Ela tem 157 títulos e **cada um foi
conferido no LRCLIB** (as colunas `lrclib_ids` e `duracoes_s` guardam a prova). Seis faixas que são MPB e
não forró (Girassol, Dia Branco...) ficaram de fora. Essa lista é curadoria e não dataset; na
apresentação, deixar isso claro.

**LRCLIB (lrclib.net).** Base comunitária e gratuita de letras sincronizadas. Não exige chave. A cobertura
é boa para clássicos e forró eletrônico e ruim para gravações de nicho: das 106 faixas do BYRM,
a maioria das de Santanna, Trio Forrozão e Os Gonzagas não tem letra sincronizada.

O resultado faixa a faixa está em `data/relatorio_catalogo.md`.

## Clima e energia das músicas novas

O matching é *fail closed*: num veto de clima ("nada romântico"), música **sem** clima é bloqueada.
Por isso toda música nova precisa de `mood` e `energy`. Eles estão em `data/curadoria_forro.json`, com
`source = `curadoria_ia_2026-11-08_revisar``.

A classificação foi **proposta por IA** a partir do trecho da letra e do estilo da faixa (xote, baião,
arrasta-pé, forró eletrônico romântico...). É uma proposta para a equipe revisar, não uma validação.
Climas usados: `animada`, `festiva`, `romantica`, `tranquila` (já existiam), `saudosa` (nova: saudade
da terra ou de alguém, que não é o mesmo que romântico) e `sofrida` (nova: dor de cotovelo, para que
"não quero sofrência" vire um veto que funcione). Cada entrada tem um campo `evidence` com o trecho
da letra ou o estilo que justificou a escolha. Como o prompt de interpretação recebe os climas do
catálogo, a IA passa a reconhecer os dois novos sem mudança em `llm.py`.

## Como rodar

```bash
# 1. (opcional) regenerar o catálogo; usa cache em data/.cache
python3 scripts/build_catalog.py --ufmg-max 45
python3 scripts/validate_seed.py

# 2. banco: a migração 0002 adiciona kind/lyrics_lrc/lyrics_source
alembic -c backend/alembic.ini upgrade head
python3 scripts/import_catalog.py   # importa piloto + catalogo_forro.json (idempotente)

# 3. testes (inclui backend/tests/test_catalogo_letras.py)
PYTHONPATH=backend pytest -q backend/tests
```

No Render nada muda: o `Dockerfile` já roda `alembic upgrade head` e `import_catalog.py` ao subir, e
`data/` (com `data/letras/*.lrc`) é copiada para a imagem. O deploy **não** acessa LRCLIB nem a busca do
YouTube.

Para adicionar uma música à mão: inclua no `catalogo_forro.json` com um `.lrc` em `data/letras/`, ou
acrescente a linha na fonte e rode o script de novo. Para tirar uma música, use
`"excluir": "motivo"` em `ajustes_byrm.json` (BYRM) ou apague a entrada.

## Limitações (dizer na apresentação)

- **Voz original.** A versão `letra_sincronizada` toca a música com o cantor; não é instrumental.
  Funciona como "cante junto". Remover a voz exigiria processar o áudio, o que está fora do escopo
  (e o áudio do YouTube não é acessível no navegador).
- **`approved=true`** significa que o vídeo tocou no player incorporado em `/verificar.html` e que a
  duração bate com a letra. Os donos podem bloquear a incorporação a qualquer momento; se acontecer
  durante a apresentação, o player mostra o erro e o link para o YouTube.
- **Letras comunitárias.** Podem ter erros de digitação ou de tempo. O botão ±0,5 s corrige atrasos
  pequenos durante a apresentação.
- **Direitos.** `rights_reviewed=false` em tudo, como no piloto. Os vídeos são reproduzidos pelo player
  oficial do YouTube e as letras só são exibidas, não redistribuídas fora do protótipo acadêmico.
- **Busca no YouTube.** O script lê a página pública de resultados; se o YouTube mudar o HTML, a busca
  para de achar vídeos novos, mas o catálogo já gerado continua funcionando.
