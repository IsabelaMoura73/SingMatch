import { CheckCircle2, ExternalLink, Play, SkipBack, SkipForward } from 'lucide-react'
import type { Script } from '../api'
import { KaraokePlayer } from '../KaraokePlayer'
import { EnergyBar, type SongLookup } from './Room'

/** Player do organizador: aparece só no dispositivo dele, depois de aprovar o roteiro. */
export function PlayerCard({ script, index, lookup, participantName, onSelect }: {
  script: Script
  /** Apresentação aberta; null enquanto o player não foi aberto. */
  index: number | null
  lookup: SongLookup
  participantName: (ids: string[]) => string
  onSelect: (index: number) => void
}) {
  return (
    <section className="sm-card flex flex-col gap-5 border-primary/40" aria-labelledby="player-titulo">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <span className="text-xs font-bold tracking-[0.18em] text-accent">HORA DE CANTAR</span>
          <h2 id="player-titulo" className="mt-1 mb-0 text-2xl font-bold">Player do organizador</h2>
        </div>
        <span className="sm-chip bg-neon/15 text-neon"><CheckCircle2 className="h-3 w-3" aria-hidden="true" />Repertório aprovado</span>
      </div>

      {index === null ? (
        <>
          <p className="m-0 text-muted-foreground">
            Toque na ordem do roteiro. Use “Tela cheia” na TV ou no projetor. O player aparece só aqui, no seu dispositivo.
          </p>
          <button type="button" className="sm-btn-primary self-start px-6 py-3 text-base" onClick={() => onSelect(0)}>
            <Play className="h-5 w-5" aria-hidden="true" />Abrir o player
          </button>
        </>
      ) : (
        <PlayerView script={script} index={index} lookup={lookup} participantName={participantName} onSelect={onSelect} />
      )}

      <p className="m-0 text-xs text-muted-foreground">
        Vídeos incorporados do YouTube. A disponibilidade pode mudar; a aprovação do piloto não equivale a revisão de direitos.
      </p>
    </section>
  )
}

function PlayerView({ script, index, lookup, participantName, onSelect }: {
  script: Script
  index: number
  lookup: SongLookup
  participantName: (ids: string[]) => string
  onSelect: (index: number) => void
}) {
  const item = script.items[index]
  const version = lookup.versionsById.get(item.karaoke_version_id)
  const song = version ? lookup.songsById.get(version.song_id) : undefined
  // Somente versões aprovadas e do tipo karaoke (regra do PR "karaoke-only").
  const playable = version?.approved === true && version.kind === 'karaoke'
  const last = script.items.length - 1

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(240px,0.7fr)]">
      <div className="flex min-w-0 flex-col gap-4">
        <div className="text-center">
          <p className="m-0 text-xs tracking-widest text-accent uppercase">Apresentação {index + 1} de {script.items.length}</p>
          <p className="mt-3 mb-0 text-sm text-muted-foreground">No microfone</p>
          <p className="m-0 font-display text-3xl font-extrabold text-primary sm:text-4xl">{participantName(item.participant_ids)}</p>
          <h3 className="mt-3 mb-0 text-2xl font-extrabold sm:text-3xl">{song?.title ?? item.karaoke_version_id}</h3>
          {song && <p className="mt-1 mb-0 text-muted-foreground">{song.artists.join(', ')}</p>}
          <div className="mt-2 flex justify-center"><EnergyBar level={song?.energy ?? null} /></div>
        </div>

        {playable && version ? (
          <>
            <KaraokePlayer key={version.id} version={version} />
            <a
              className="inline-flex items-center gap-1 self-center text-xs text-neon hover:underline"
              href={`https://www.youtube.com/watch?v=${version.youtube_video_id}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Vídeo não carregou? Abrir no YouTube <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </>
        ) : (
          <p role="status" className="m-0 rounded-xl border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-accent">
            Esta música não tem uma versão de karaokê aprovada. Edite ou gere um novo roteiro para escolher um karaokê válido.
          </p>
        )}

        <div className="flex items-center justify-center gap-4">
          <button type="button" aria-label="Apresentação anterior" disabled={index === 0} onClick={() => onSelect(index - 1)}
            className="grid h-12 w-12 place-items-center rounded-full border-0 bg-secondary p-0 text-foreground hover:text-primary disabled:opacity-30">
            <SkipBack className="h-5 w-5" aria-hidden="true" />
          </button>
          <button type="button" disabled={index === last} onClick={() => onSelect(index + 1)} className="sm-btn-primary px-6 py-3">
            Próxima apresentação<SkipForward className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      <aside aria-labelledby="fila-titulo">
        <h3 id="fila-titulo" className="mt-0 mb-2 text-xs font-bold tracking-widest text-muted-foreground uppercase">Fila de apresentações</h3>
        <ol className="m-0 flex flex-col gap-1 p-0">
          {script.items.map((entry, i) => {
            const v = lookup.versionsById.get(entry.karaoke_version_id)
            const s = v ? lookup.songsById.get(v.song_id) : undefined
            const state = i === index ? 'bg-primary/15 text-primary' : i < index ? 'bg-transparent text-muted-foreground hover:bg-secondary' : 'bg-transparent text-foreground hover:bg-secondary'
            return (
              <li key={entry.position} className="list-none">
                <button
                  type="button"
                  aria-current={i === index ? 'true' : undefined}
                  onClick={() => onSelect(i)}
                  className={`flex w-full items-start gap-3 rounded-xl border-0 px-3 py-2 text-left text-sm ${state}`}
                >
                  <span className="font-display font-extrabold opacity-60">{String(i + 1).padStart(2, '0')}</span>
                  <span className="flex min-w-0 flex-col">
                    <span className={`font-semibold ${i < index ? 'line-through' : ''}`}>{s?.title ?? entry.karaoke_version_id}</span>
                    <span className="text-xs text-muted-foreground">{participantName(entry.participant_ids)}{s ? ` · ${s.artists.join(', ')}` : ''}</span>
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      </aside>
    </div>
  )
}
