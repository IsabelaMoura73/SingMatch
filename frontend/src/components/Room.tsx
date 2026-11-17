import { useState, type ReactNode } from 'react'
import {
  ArrowDown, ArrowUp, Check, CheckCircle2, Clock, Copy, Crown, Pencil, RefreshCw, Sparkles, Trash2, TriangleAlert, Users, X,
} from 'lucide-react'
import { characteristicLabel } from '../labels'
import type { KaraokeVersion, Participant, Room, Script, ScriptItem, ScriptProposal, Song } from '../api'

export type SongLookup = {
  songsById: Map<string, Song>
  versionsById: Map<string, KaraokeVersion>
}

function initials(name: string) {
  return name.trim().slice(0, 2).toUpperCase() || '♪'
}

/** Pequeno aviso dentro dos cards (informação, atenção ou erro). */
function Note({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'error'; children: ReactNode }) {
  const toneClass = {
    info: 'border-border bg-background/40 text-muted-foreground',
    warn: 'border-accent/40 bg-accent/10 text-accent',
    error: 'border-destructive/40 bg-destructive/10 text-destructive',
  }[tone]
  return <p role={tone === 'info' ? undefined : 'status'} className={`mb-0 rounded-xl border px-4 py-3 text-sm ${toneClass}`}>{children}</p>
}

/** Selo para apresentações em dupla. */
export function DuetChip() {
  return <span className="sm-chip bg-neon/15 text-neon"><Users className="h-3 w-3" aria-hidden="true" />Dueto</span>
}

export function EnergyBar({ level }: { level: number | null }) {
  if (level === null) return null
  return (
    <span className="flex items-end gap-0.5" title={`Energia ${level}/5`} aria-label={`Energia ${level} de 5`} role="img">
      {[1, 2, 3, 4, 5].map(n => (
        <span key={n} className={`w-1 rounded-sm ${n <= level ? 'bg-energy' : 'bg-muted'}`} style={{ height: 4 + n * 3 }} />
      ))}
    </span>
  )
}

/** Cabeçalho da sala: papel, intenção e código para compartilhar. */
export function RoomHeader({ isHost, intention, code, onCopy }: {
  isHost: boolean
  intention: string | undefined
  code: string | undefined
  onCopy: () => void
}) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    onCopy()
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="flex flex-col gap-5 pt-2 pb-1 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <span className="text-xs font-bold tracking-[0.18em] text-accent">{isHost ? 'PAINEL DO ORGANIZADOR' : 'MEU ESPAÇO NO KARAOKÊ'}</span>
        <h1 className="mt-2 mb-2 text-4xl leading-tight font-extrabold sm:text-5xl">{isHost ? 'A noite é nossa.' : 'Sua voz faz parte.'}</h1>
        <p className="mb-0 text-muted-foreground">Forró · {intention || 'Uma noite de música criada em grupo'}</p>
      </div>
      <div className="sm-card shrink-0 px-6 py-4 text-center">
        <p className="mb-1 text-xs text-muted-foreground">Código da sala</p>
        {isHost ? (
          <button type="button" onClick={copy} className="inline-flex items-center gap-3 border-0 bg-transparent p-0 font-mono text-3xl font-bold tracking-[0.25em] text-hot" aria-label="Copiar código da sala">
            {code || '········'}<Copy className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
          </button>
        ) : (
          <strong className="font-mono text-3xl tracking-[0.25em] text-hot">{code || '········'}</strong>
        )}
        {isHost && <p className="mt-1 mb-0 h-4 text-xs text-accent" aria-live="polite">{copied ? 'Copiado!' : 'Toque para copiar'}</p>}
      </div>
    </div>
  )
}

/** Lista de quem está na sala e quem já confirmou o perfil. */
export function ParticipantsCard({ participants, meId, hostParticipantId, onRefresh, onRemove, removingId, busy = false }: {
  participants: Participant[]
  meId: string | undefined
  /**
   * Participante que é o organizador. A API não informa isso; só é conhecido no
   * dispositivo do próprio organizador (quando ele também canta).
   */
  hostParticipantId?: string
  onRefresh: () => void
  /** Só o organizador recebe esta ação: remover alguém da sala. */
  onRemove?: (person: Participant) => void
  removingId?: string | null
  busy?: boolean
}) {
  const ready = participants.filter(p => p.profile_confirmed).length
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  return (
    <section className="sm-card" aria-labelledby="participantes-titulo">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 id="participantes-titulo" className="m-0 text-xl font-bold">Quem está na sala</h2>
        <span className="flex items-center gap-2">
          <span className="sm-chip bg-secondary">{ready}/{participants.length} confirmados</span>
          <button type="button" onClick={onRefresh} className="sm-btn-ghost px-3 py-1.5 text-xs">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />Atualizar
          </button>
        </span>
      </div>
      {participants.length === 0 ? (
        <Note>Ninguém entrou ainda. Compartilhe o código da sala.</Note>
      ) : (
        <ul className="m-0 divide-y divide-border p-0">
          {participants.map(person => (
            <li key={person.id} className="flex list-none flex-wrap items-center justify-between gap-3 py-3">
              <span className="flex min-w-0 items-center gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-secondary text-xs font-bold">{initials(person.name)}</span>
                <span className="truncate">{person.name}{person.id === meId && <span className="text-muted-foreground"> (você)</span>}</span>
                {person.id === hostParticipantId && (
                  <Crown className="h-4 w-4 shrink-0 text-accent" role="img" aria-label="Organizador" />
                )}
              </span>
              {onRemove && confirmingId === person.id ? (
                <span className="ml-auto flex shrink-0 items-center gap-2">
                  <span className="text-xs text-muted-foreground">Remover da sala?</span>
                  <button type="button" className="sm-btn-ghost px-3 py-1.5 text-xs" onClick={() => setConfirmingId(null)}>Cancelar</button>
                  <button type="button" disabled={busy}
                    className="inline-flex items-center gap-1 rounded-full border border-destructive/40 bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive disabled:opacity-50"
                    onClick={() => { setConfirmingId(null); onRemove(person) }}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />Remover
                  </button>
                </span>
              ) : (
                <span className="flex shrink-0 items-center gap-2">
                  {person.profile_confirmed
                    ? <span className="sm-chip bg-neon/15 text-neon uppercase"><Check className="h-3 w-3" aria-hidden="true" />confirmado</span>
                    : <span className="sm-chip bg-muted text-muted-foreground uppercase"><Clock className="h-3 w-3" aria-hidden="true" />editando…</span>}
                  {onRemove && (
                    <button type="button" disabled={busy} onClick={() => setConfirmingId(person.id)}
                      aria-label={`Remover ${person.name} da sala`} title="Remover da sala"
                      className="grid h-8 w-8 place-items-center rounded-lg border-0 bg-transparent p-0 text-muted-foreground hover:text-destructive disabled:opacity-30">
                      {removingId === person.id ? <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Trash2 className="h-4 w-4" aria-hidden="true" />}
                    </button>
                  )}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 mb-0 text-xs text-muted-foreground">Atualização automática a cada 7 segundos.</p>
    </section>
  )
}

/** Uma apresentação do roteiro (somente leitura). */
function ScriptRow({ item, index, personName, lookup }: {
  item: ScriptItem
  index: number
  personName: string
  lookup: SongLookup
}) {
  const version = lookup.versionsById.get(item.karaoke_version_id)
  const song = version ? lookup.songsById.get(version.song_id) : undefined
  return (
    <li className="flex list-none gap-4 rounded-2xl border border-border bg-background/40 p-4">
      <span className="font-display text-2xl font-extrabold text-muted-foreground">{String(index + 1).padStart(2, '0')}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="mb-0 font-bold">
            {song?.title ?? item.karaoke_version_id}
            {song && <span className="font-normal text-muted-foreground"> — {song.artists.join(', ')}</span>}
          </p>
          <span className="flex items-center gap-2">
            {item.participant_ids.length === 2 && <DuetChip />}
            <EnergyBar level={song?.energy ?? null} />
            <span className={`sm-chip ${item.origin === 'ia' ? 'bg-primary/15 text-primary' : 'bg-secondary text-secondary-foreground'}`}>
              {item.origin === 'ia' ? '✧ IA' : 'Manual'}
            </span>
          </span>
        </div>
        <p className="mb-0 text-sm">
          <span className="text-primary">{personName}</span>
          {song?.mood && <span className="text-muted-foreground"> · {characteristicLabel(song.mood)}</span>}
        </p>
        <p className="mt-1 mb-0 text-xs text-muted-foreground">
          {item.justification || (item.origin === 'manual' ? 'Escolha editada pelo organizador.' : 'Apresentação sugerida.')}
        </p>
      </div>
    </li>
  )
}

function ScriptList({ script, participantName, lookup }: {
  script: Pick<Script, 'items'>
  participantName: (ids: string[]) => string
  lookup: SongLookup
}) {
  return (
    <ol className="m-0 space-y-2 p-0">
      {script.items.map((item, i) => (
        <ScriptRow key={item.position} item={item} index={i} personName={participantName(item.participant_ids)} lookup={lookup} />
      ))}
    </ol>
  )
}

function StatusChip({ script }: { script: Script }) {
  return script.approved
    ? <span className="sm-chip bg-neon/15 text-neon"><CheckCircle2 className="h-3 w-3" aria-hidden="true" />Aprovado</span>
    : <span className="sm-chip bg-secondary">✧ Proposta · v{script.version}</span>
}

/** Roteiro visto por quem não é organizador: só leitura. */
export function ParticipantScriptCard({ script, participantName, lookup }: {
  script: Script
  participantName: (ids: string[]) => string
  lookup: SongLookup
}) {
  return (
    <section className="sm-card flex flex-col gap-4" aria-labelledby="roteiro-titulo">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="roteiro-titulo" className="m-0 text-2xl font-bold">Roteiro da noite</h2>
          <p className="mt-1 mb-0 text-sm text-muted-foreground">{script.title} · {script.items.length} músicas</p>
        </div>
        <StatusChip script={script} />
      </div>
      <ScriptList script={script} participantName={participantName} lookup={lookup} />
      <Note>
        {script.approved ? 'O organizador aprovou este roteiro.' : 'Esta ainda é uma proposta: o organizador pode editá-la.'}
        {' '}O player fica só no dispositivo do organizador.
      </Note>
    </section>
  )
}

/** Roteiro do organizador: gerar com IA, editar (trocar música/ordem) e aprovar. */
export function HostScriptCard({
  room, participantName, lookup, eligibleVideos, busy, pending,
  editing, proposal, editVersion,
  onGenerate, onStartEdit, onCancelEdit, onSaveEdit, onApprove, onTitleChange, onChangeItem, onMoveItem,
}: {
  room: Room
  participantName: (ids: string[]) => string
  lookup: SongLookup
  eligibleVideos: KaraokeVersion[]
  busy: boolean
  pending: 'generate' | 'save' | 'approve' | null
  editing: boolean
  proposal: ScriptProposal | null
  editVersion: number | null
  onGenerate: () => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  onApprove: () => void
  onTitleChange: (title: string) => void
  onChangeItem: (index: number, update: Partial<ScriptItem>) => void
  onMoveItem: (index: number, offset: number) => void
}) {
  const script = room.script
  const allReady = room.participants.length > 0 && room.participants.every(p => p.profile_confirmed)
  const stale = !!script && script.input_revision !== room.session.revision
  const conflict = !!script && editing && editVersion !== script.version

  return (
    <section className="sm-card flex flex-col gap-4" aria-labelledby="roteiro-titulo">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="roteiro-titulo" className="m-0 text-2xl font-bold">Roteiro da noite</h2>
          <p className="mt-1 mb-0 text-sm text-muted-foreground">
            {script ? `${script.title} · versão ${script.version} · ${script.items.length} músicas` : 'Uma apresentação por pessoa, solo ou em dueto quando os dois toparem, com músicas aprovadas do catálogo.'}
          </p>
        </div>
        {script && <StatusChip script={script} />}
      </div>


      {script && editing && proposal && (
        <div className="flex flex-col gap-3">
          <Note tone="warn">Modo de edição: troque músicas ou mude a ordem. Ninguém pode ser removido da rodada, e as duplas continuam as mesmas.</Note>
          {conflict && <Note tone="error">Outra versão foi salva enquanto você editava. Cancele e atualize a sala antes de continuar.</Note>}
          <label className="block text-sm font-semibold">
            Título do roteiro
            <input className="sm-input mt-1" maxLength={160} required value={proposal.title} onChange={e => onTitleChange(e.target.value)} />
          </label>
          <ol className="m-0 space-y-2 p-0">
            {proposal.items.map((item, i) => {
              const name = participantName(item.participant_ids)
              const taken = new Set(proposal.items.filter((_, j) => j !== i).map(x => x.karaoke_version_id))
              const duet = item.participant_ids.length === 2
              // Dueto: só músicas marcadas para dueto (o servidor recusa as outras).
              const options = eligibleVideos.filter(v => v.id === item.karaoke_version_id || (
                !taken.has(v.id) && (!duet || lookup.songsById.get(v.song_id)?.duet_possible === true)))
              return (
                <li key={item.participant_ids.join('-')} className="flex list-none gap-3 rounded-2xl border border-border bg-background/40 p-4">
                  <span className="font-display text-2xl font-extrabold text-muted-foreground">{String(i + 1).padStart(2, '0')}</span>
                  <div className="min-w-0 flex-1">
                    <p className="mb-1 flex items-center gap-2 text-sm text-primary">{name}{duet && <DuetChip />}</p>
                    <select
                      className="sm-input py-2 text-sm"
                      aria-label={`Música de ${name}`}
                      value={item.karaoke_version_id}
                      onChange={e => onChangeItem(i, { karaoke_version_id: e.target.value })}
                    >
                      {options.map(video => {
                        const song = lookup.songsById.get(video.song_id)
                        return <option key={video.id} value={video.id}>{song?.title || video.id} — {song?.artists.join(', ')}{song?.energy ? ` (energia ${song.energy})` : ''}</option>
                      })}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <button type="button" aria-label={`Subir apresentação de ${name}`} onClick={() => onMoveItem(i, -1)} disabled={i === 0}
                      className="grid h-8 w-8 place-items-center rounded-lg border-0 bg-secondary p-0 text-foreground hover:text-primary disabled:opacity-30">
                      <ArrowUp className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button type="button" aria-label={`Descer apresentação de ${name}`} onClick={() => onMoveItem(i, 1)} disabled={i === proposal.items.length - 1}
                      className="grid h-8 w-8 place-items-center rounded-lg border-0 bg-secondary p-0 text-foreground hover:text-primary disabled:opacity-30">
                      <ArrowDown className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                </li>
              )
            })}
          </ol>
          <p className="mb-0 text-xs text-muted-foreground">O servidor confere os vetos de cada pessoa ao salvar e recusa músicas vetadas. Num dueto, a música precisa servir para as duas pessoas.</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="sm-btn-ghost" onClick={onCancelEdit}><X className="h-4 w-4" aria-hidden="true" />Cancelar</button>
            <button type="button" className="sm-btn-primary flex-1" onClick={onSaveEdit} disabled={busy || conflict || !proposal.title.trim()}>
              <Check className="h-4 w-4" aria-hidden="true" />{pending === 'save' ? 'Salvando…' : 'Salvar alterações'}
            </button>
          </div>
        </div>
      )}

      {script && !editing && (
        <>
          <ScriptList script={script} participantName={participantName} lookup={lookup} />
          {stale && (
            <Note tone="warn">
              <TriangleAlert className="mr-1 inline h-4 w-4 align-[-3px]" aria-hidden="true" />
              Os perfis mudaram desde esta proposta. Gere um novo roteiro antes de aprovar.
            </Note>
          )}
          <div className="flex flex-wrap gap-2 rounded-3xl border border-border bg-card/95 p-2 sm:rounded-full">
            <button type="button" className="sm-btn-ghost" onClick={onStartEdit} disabled={busy}>
              <Pencil className="h-4 w-4" aria-hidden="true" />Editar
            </button>
            <button type="button" className="sm-btn-ghost" onClick={onGenerate} disabled={busy || !allReady} title={allReady ? undefined : 'Aguardando todos confirmarem'}>
              <RefreshCw className={`h-4 w-4 ${pending === 'generate' ? 'animate-spin' : ''}`} aria-hidden="true" />
              {pending === 'generate' ? 'Gerando…' : 'Gerar outro'}
            </button>
            {!script.approved && (
              <button type="button" className="sm-btn-primary flex-1" onClick={onApprove} disabled={busy || stale}>
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />{pending === 'approve' ? 'Aprovando…' : 'Aprovar roteiro'}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  )
}

/** Próximo passo na tela "Sala": completar o perfil, gerar o roteiro ou ir até ele. */
export function LobbyActions({
  isHost, singing, profileConfirmed, hasScript, allReady, generating, busy, onProfile, onGenerate, onScript,
}: {
  isHost: boolean
  /** Esta aba também é participante (canta). */
  singing: boolean
  profileConfirmed: boolean
  hasScript: boolean
  allReady: boolean
  generating: boolean
  busy: boolean
  onProfile: () => void
  onGenerate: () => void
  onScript: () => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {singing && (
        <button type="button" className={profileConfirmed ? 'sm-btn-ghost' : 'sm-btn-primary'} onClick={onProfile} disabled={busy}>
          {profileConfirmed ? 'Editar meu perfil' : 'Preencher meu perfil'}
        </button>
      )}
      {hasScript ? (
        <button type="button" className="sm-btn-primary flex-1" onClick={onScript}>Ver roteiro</button>
      ) : isHost ? (
        <button type="button" className="sm-btn-primary flex-1" onClick={onGenerate} disabled={busy || !allReady}>
          <Sparkles className={`h-4 w-4 ${generating ? 'animate-spin' : ''}`} aria-hidden="true" />
          {generating ? 'Montando o roteiro…' : allReady ? 'Gerar roteiro com IA' : 'Aguardando todos confirmarem'}
        </button>
      ) : (
        <p className="m-0 flex-1 text-sm text-muted-foreground">
          {profileConfirmed ? 'Pronto! O organizador vai gerar o roteiro quando todos confirmarem.' : 'Confirme seu perfil para entrar no roteiro.'}
        </p>
      )}
    </div>
  )
}
