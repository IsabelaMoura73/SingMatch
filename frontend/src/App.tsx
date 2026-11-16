import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  api, type Catalog, type KaraokeVersion, type OwnProfile, type Song,
  type Profile, type Room,
  type Script, type ScriptItem, type ScriptProposal,
} from './api'
import { KaraokePlayer } from './KaraokePlayer'
import { Shell } from './components/Shell'
import { Home } from './components/Home'
import { ProfileCard } from './components/Profile'
import { HostScriptCard, ParticipantScriptCard, ParticipantsCard, RoomHeader, type SongLookup } from './components/Room'

const STORAGE_KEY = 'singmatch:mvp:identity'
/**
 * Acesso desta aba à sala. O organizador pode também ser participante (cantar):
 * nesse caso guardamos os dois tokens. Pelo menos um dos dois existe.
 */
type Identity = {
  sessionId: string
  hostToken?: string
  participant?: { id: string; token: string }
}
/** Token usado para ler o estado da sala (qualquer papel serve). */
const roomToken = (identity: Identity) => identity.hostToken ?? identity.participant!.token

type ActiveTask = 'create' | 'join' | 'join-host' | 'interpret' | 'confirm' | 'generate' | 'save' | 'approve' | null

function storedIdentity(): Identity | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    const data = parsed as Record<string, unknown>
    if (typeof data.sessionId !== 'string') return null
    // Formato antigo (um papel por aba), salvo antes da credencial dupla.
    if (typeof data.token === 'string') {
      if (data.role === 'host') return { sessionId: data.sessionId, hostToken: data.token }
      if (data.role === 'participant' && typeof data.participantId === 'string') {
        return { sessionId: data.sessionId, participant: { id: data.participantId, token: data.token } }
      }
      return null
    }
    const hostToken = typeof data.hostToken === 'string' ? data.hostToken : undefined
    const p = data.participant as Record<string, unknown> | undefined
    const participant = p && typeof p.id === 'string' && typeof p.token === 'string' ? { id: p.id, token: p.token } : undefined
    if (hostToken || participant) return { sessionId: data.sessionId, hostToken, participant }
  } catch { /* sessão antiga inválida */ }
  return null
}

function displayError(err: unknown): string {
  return err instanceof Error ? err.message : 'Ocorreu um erro inesperado. Tente novamente.'
}
function cloneProposal(script: Script): ScriptProposal {
  return { title: script.title, items: script.items.map(item => ({ ...item, participant_ids: [...item.participant_ids] })) }
}


function SongName({versionId, catalog}: {versionId: string; catalog: Catalog | null}) {
  const video = catalog?.karaoke_versions.find(v => v.id === versionId)
  const song = catalog?.songs.find(s => s.id === video?.song_id)
  if (!song) return <strong>{versionId}</strong>
  return <><strong>{song.title}</strong><span className="muted">{song.artists.join(', ')} · Energia {song.energy ?? '?'} / 5 {song.mood ? `· ${song.mood}` : ''}{' (karaokê)'}</span></>
}

function App() {
  const [identity, setIdentity] = useState<Identity | null>(storedIdentity)
  const [room, setRoom] = useState<Room | null>(null)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [own, setOwn] = useState<OwnProfile | null>(null)
  const [rawText, setRawText] = useState('')
  const [interpretedText, setInterpretedText] = useState('')
  const [draft, setDraft] = useState<Profile | null>(null)
  const [initialCode] = useState(() => new URLSearchParams(window.location.search).get('code') || '')
  const [hostJoinName, setHostJoinName] = useState('')
  const [pending, setPending] = useState<ActiveTask>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [connected, setConnected] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editVersion, setEditVersion] = useState<number | null>(null)
  const [proposal, setProposal] = useState<ScriptProposal | null>(null)
  const [playingIndex, setPlayingIndex] = useState<number | null>(null)

  const saveIdentity = (newIdentity: Identity) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(newIdentity))
    setRoom(null)
    setOwn(null)
    setDraft(null)
    setIdentity(newIdentity)
    window.history.replaceState(null, '', window.location.pathname)
    setError('')
    setMessage('')
  }

  const refresh = useCallback(async (target: Identity) => {
    const data = await api.room(target.sessionId, roomToken(target))
    setRoom(data)
    setConnected(true)
    return data
  }, [])

  useEffect(() => {
    let alive = true
    api.catalog().then(v => { if (alive) setCatalog(v) }).catch(() => { /* sala mostrará conexão */ })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!identity) return
    let alive = true
    const poll = () => {
      api.room(identity.sessionId, roomToken(identity))
        .then(data => { if (alive) { setRoom(data); setConnected(true) } })
        .catch(() => { if (alive) setConnected(false) })
    }
    poll()
    const timer = window.setInterval(poll, 7000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [identity])

  const me = identity?.participant
  useEffect(() => {
    if (!me) return
    let alive = true
    api.ownProfile(me.id, me.token).then(profile => {
      if (!alive) return
      setOwn(profile)
      setRawText(profile.text || '')
      setInterpretedText(profile.text || '')
      setDraft(profile.confirmed || profile.draft)
    }).catch(err => { if (alive) setError(displayError(err)) })
    return () => { alive = false }
  }, [me?.id, me?.token])

  const execute = async (task: NonNullable<ActiveTask>, fn: () => Promise<void>) => {
    setPending(task)
    setError('')
    setMessage('')
    try { await fn() }
    catch (err) { setError(displayError(err)) }
    finally { setPending(null) }
  }

  const createRoom = async (intention: string, hostName: string | null) => {
    await execute('create', async () => {
      const result = await api.create(intention)
      const created: Identity = { sessionId: result.session.id, hostToken: result.host_token }
      if (hostName) {
        // Segunda chamada: o organizador entra como participante para também cantar.
        try {
          const joined = await api.join(result.session.code, hostName)
          created.participant = { id: joined.participant_id, token: joined.participant_token }
        } catch (err) {
          // A sala já existe: entra como organizador e oferece tentar de novo na sala.
          saveIdentity(created)
          setHostJoinName(hostName)
          throw new Error(`Sala criada, mas não foi possível incluir você como participante. ${displayError(err)} Tente de novo em “Entrar também como participante”.`)
        }
      }
      saveIdentity(created)
    })
  }
  const joinRoom = async (code: string, name: string) => {
    await execute('join', async () => {
      const data = await api.join(code, name)
      saveIdentity({ sessionId: data.session_id, participant: { id: data.participant_id, token: data.participant_token } })
    })
  }
  const joinAsHost = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!identity?.hostToken || !room || identity.participant) return
    const current = identity
    await execute('join-host', async () => {
      const joined = await api.join(room.session.code, hostJoinName.trim())
      const updated: Identity = { ...current, participant: { id: joined.participant_id, token: joined.participant_token } }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
      setIdentity(updated)
      await refresh(updated)
      setMessage('Pronto! Agora conte o que você gosta de cantar.')
    })
  }
  const exitRoom = () => {
    if (!window.confirm('Sair apaga deste navegador o acesso à sala. Sem o token, não será possível recuperar o papel de organizador ou este participante. Deseja sair?')) return
    sessionStorage.removeItem(STORAGE_KEY)
    setIdentity(null); setRoom(null); setOwn(null); setDraft(null)
    setPlayingIndex(null); setEditing(false); setError(''); setMessage('')
  }
  const copyCode = async () => {
    if (!room) return
    try { await navigator.clipboard.writeText(room.session.code); setMessage('Código copiado. Compartilhe com seus amigos.') }
    catch { setMessage(`Compartilhe este código: ${room.session.code}`) }
  }
  const interpret = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!identity || !identity.participant) return
    const current = identity, person = identity.participant
    await execute('interpret', async () => {
      const result = await api.interpret(person.id, person.token, rawText.trim())
      setDraft(result.draft)
      setInterpretedText(rawText.trim())
      setOwn(old => old ? { ...old, text: rawText.trim(), draft: result.draft, confirmed: null } : null)
      await refresh(current)
      setMessage('Perfil interpretado. Revise e confirme abaixo.')
    })
  }
  const confirm = async () => {
    if (!identity || !identity.participant || !draft) return
    const current = identity, person = identity.participant
    if (rawText.trim() !== interpretedText) { setError('O texto mudou. Clique em “Interpretar com IA” novamente antes de confirmar.'); return }
    await execute('confirm', async () => {
      const result = await api.confirm(person.id, person.token, draft)
      setOwn(result)
      setDraft(result.confirmed)
      await refresh(current)
      setMessage('Preferências confirmadas! Você já pode aguardar o roteiro.')
    })
  }
  const generate = async () => {
    if (!identity?.hostToken) return
    if (room?.script?.approved && !window.confirm('Gerar outro roteiro invalidará a aprovação atual. Continuar?')) return
    const host = identity, hostToken = identity.hostToken
    await execute('generate', async () => {
      await api.generate(host.sessionId, hostToken)
      await refresh(host)
      setEditing(false); setPlayingIndex(null)
      setMessage('Roteiro gerado! Confira antes de aprovar.')
    })
  }
  const startEdit = (script: Script) => {
    setProposal(cloneProposal(script))
    setEditVersion(script.version)
    setEditing(true)
    setError(''); setMessage('')
  }
  const changeItem = (i: number, update: Partial<ScriptItem>) => {
    setProposal(old => old ? {
      ...old, items: old.items.map((item, index) => index === i ? { ...item, ...update, origin: 'manual', justification: null } : item),
    } : old)
  }
  const moveItem = (i: number, offset: number) => {
    setProposal(old => {
      if (!old) return old
      const j = i + offset
      if (j < 0 || j >= old.items.length) return old
      const items = [...old.items]
      ;[items[i], items[j]] = [items[j], items[i]]
      return { ...old, items: items.map((item, index) => ({ ...item, position: index + 1, origin: 'manual' as const, justification: null })) }
    })
  }
  const saveEdit = async () => {
    if (!identity?.hostToken || !proposal || editVersion === null) return
    if (new Set(proposal.items.map(i => i.karaoke_version_id)).size !== proposal.items.length) {
      setError('Uma música não pode se repetir no roteiro. Escolha vídeos diferentes.'); return
    }
    const host = identity, hostToken = identity.hostToken
    await execute('save', async () => {
      await api.edit(host.sessionId, hostToken, editVersion, proposal)
      await refresh(host)
      setEditing(false); setPlayingIndex(null)
      setMessage('Nova versão do roteiro salva. Aprove-a para reproduzir.')
    })
  }
  const approve = async () => {
    if (!identity?.hostToken || !room?.script) return
    const host = identity, hostToken = identity.hostToken
    await execute('approve', async () => {
      await api.approve(host.sessionId, hostToken, room.script!.version)
      await refresh(host)
      setMessage('Roteiro aprovado! O player está liberado neste dispositivo.')
    })
  }

  const songsById = useMemo(() => new Map<string, Song>((catalog?.songs ?? []).map(song => [song.id, song] as const)), [catalog])
  const versionsById = useMemo(() => new Map<string, KaraokeVersion>((catalog?.karaoke_versions ?? []).map(video => [video.id, video] as const)), [catalog])
  const eligibleVideos = useMemo(
    () => (catalog?.karaoke_versions || []).filter(
      v =>
        v.approved &&
        v.kind === 'karaoke' &&
        songsById.get(v.song_id)?.genre === 'forro'
    ),
    [catalog, songsById]
  )
  // Mesmos termos que backend/app/matching.py reconhece em vetos de característica.
  const tagSuggestions = useMemo(() => [
    ...new Set((catalog?.songs ?? []).map(song => song.mood).filter((mood): mood is string => !!mood)),
  ].sort().concat(['energia baixa', 'energia media', 'energia alta']), [catalog])
  const lookup: SongLookup = useMemo(() => ({ songsById, versionsById }), [songsById, versionsById])
  const isHost = !!identity?.hostToken
  const participantName = (ids: string[]) => ids.map(id => room?.participants.find(p => p.id === id)?.name || 'Participante').join(' + ')

  return (
    <Shell code={identity ? room?.session.code : undefined} onExit={identity ? exitRoom : undefined}>

      <main className="main-container">
        {!identity ? (
          <Home
            busy={pending !== null}
            creating={pending === 'create'}
            joining={pending === 'join'}
            initialCode={initialCode}
            onCreate={(intention, hostName) => { void createRoom(intention, hostName) }}
            onJoin={(code, name) => { void joinRoom(code, name) }}
          />
        ) : (
          <div className="flex flex-col gap-5">
            <RoomHeader isHost={isHost} intention={room?.session.intention} code={room?.session.code} onCopy={() => { void copyCode() }} />
            {!connected && <p role="alert" className="mb-0 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">Conexão com a API indisponível. Tentando reconectar...</p>}
            {isHost && !me && room && !['playing', 'finished'].includes(room.session.status) && (
              <form onSubmit={joinAsHost} className="sm-card flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="flex-1">
                  <p className="mb-0 font-semibold">Vai cantar também?</p>
                  <p className="mb-0 text-sm text-muted-foreground">Entre na roda com seu nome. Você ganha uma música no roteiro, como os amigos.</p>
                </div>
                <input className="sm-input sm:max-w-56" aria-label="Seu nome" placeholder="Seu nome" maxLength={80} required value={hostJoinName} onChange={e => setHostJoinName(e.target.value)} />
                <button className="sm-btn-primary shrink-0" disabled={pending !== null || !hostJoinName.trim()}>{pending === 'join-host' ? 'Entrando...' : 'Entrar também como participante'}</button>
              </form>
            )}
            {!room ? <div className="sm-card text-muted-foreground">Carregando informações da sala...</div> : <>
              <ParticipantsCard participants={room.participants} meId={me?.id} onRefresh={() => { void refresh(identity).catch(err => setError(displayError(err))) }} />

              {me && <ProfileCard
                name={room.participants.find(p => p.id === me.id)?.name || own?.name || ''}
                intention={room.session.intention}
                own={own}
                rawText={rawText}
                interpretedText={interpretedText}
                draft={draft}
                tagSuggestions={tagSuggestions}
                busy={pending !== null}
                interpreting={pending === 'interpret'}
                confirming={pending === 'confirm'}
                onTextChange={setRawText}
                onDraftChange={setDraft}
                onInterpret={interpret}
                onConfirm={() => { void confirm() }}
              />}

              {!isHost && room.script && <ParticipantScriptCard script={room.script} participantName={participantName} lookup={lookup} />}

              {isHost && <HostScriptCard
                room={room}
                participantName={participantName}
                lookup={lookup}
                eligibleVideos={eligibleVideos}
                busy={pending !== null}
                pending={pending === 'generate' || pending === 'save' || pending === 'approve' ? pending : null}
                editing={editing}
                proposal={proposal}
                editVersion={editVersion}
                onGenerate={() => { void generate() }}
                onStartEdit={() => startEdit(room.script!)}
                onCancelEdit={() => { setEditing(false); setProposal(null) }}
                onSaveEdit={() => { void saveEdit() }}
                onApprove={() => { void approve() }}
                onTitleChange={title => setProposal(old => old ? { ...old, title } : old)}
                onChangeItem={changeItem}
                onMoveItem={moveItem}
              />}

              {isHost && room.script?.approved && room.script.input_revision === room.session.revision && !editing && <section className="paper-card player-card"><div className="card-title-row"><div><span className="eyebrow">03 · HORA DE CANTAR</span><h2>Player do organizador</h2></div><span className="state-tag done">Repertório aprovado</span></div><p className="muted">Reproduza na ordem do roteiro. Músicas com letra sincronizada mostram a letra abaixo do vídeo; use “Tela cheia” na TV ou projetor. O player aparece apenas aqui, no dispositivo do organizador.</p>
                {playingIndex === null ? <button className="btn primary" type="button" onClick={() => setPlayingIndex(0)}>▶ Abrir o player</button> : <Player script={room.script} index={playingIndex} versions={versionsById} catalog={catalog} participantName={participantName} onSelect={setPlayingIndex}/>}
                <p className="muted smaller">Vídeos incorporados via YouTube. A disponibilidade e permissões de reprodução podem mudar; a aprovação do piloto não equivale a revisão de direitos.</p>
              </section>}
            </>}
          </div>
        )}
        {error && <div className="feedback error" role="alert"><strong>Não foi possível concluir</strong><span>{error}</span><button type="button" onClick={() => setError('')} aria-label="Fechar erro">×</button></div>}
        {message && <div className="feedback success" role="status"><span>{message}</span><button type="button" onClick={() => setMessage('')} aria-label="Fechar aviso">×</button></div>}
      </main>
    </Shell>
  )
}


function Player({
  script,
  index,
  versions,
  catalog,
  participantName,
  onSelect,
}: {
  script: Script
  index: number
  versions: Map<string, KaraokeVersion>
  catalog: Catalog | null
  participantName: (ids: string[]) => string
  onSelect: (index: number) => void
}) {
  const item = script.items[index]
  const version = versions.get(item.karaoke_version_id)

  // Somente versões aprovadas e do tipo karaoke.
  const isPlayable =
    version?.approved === true &&
    version.kind === 'karaoke'

  return (
    <div className="player-layout">
      <div>
        <div className="player-meta">
          <span>
            APRESENTAÇÃO {index + 1} / {script.items.length}
          </span>
          <strong>
            {participantName(item.participant_ids)}
          </strong>
        </div>

        {isPlayable && version ? (
          <>
            <KaraokePlayer
              key={version.id}
              version={version}
            />

            <a
              className="youtube-link"
              href={`https://www.youtube.com/watch?v=${version.youtube_video_id}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Vídeo não carregou? Abrir no YouTube ↗
            </a>
          </>
        ) : (
          <div className="notice warn">
            Esta música não possui uma versão de
            karaokê aprovada.

            Edite ou gere um novo roteiro para
            selecionar um karaokê válido.
          </div>
        )}

        <div className="inline-actions">
          <button
            type="button"
            className="btn outline"
            disabled={index === 0}
            onClick={() => onSelect(index - 1)}
          >
            ← Anterior
          </button>

          <button
            type="button"
            className="btn secondary"
            disabled={index === script.items.length - 1}
            onClick={() => onSelect(index + 1)}
          >
            Próxima apresentação →
          </button>
        </div>
      </div>

      <aside className="queue">
        <h3>Fila de apresentações</h3>

        {script.items.map((current, i) => (
          <button
            key={i}
            type="button"
            className={`queue-item ${
              i === index ? 'selected' : ''
            }`}
            onClick={() => onSelect(i)}
          >
            <span>
              {String(i + 1).padStart(2, '0')}
            </span>

            <div>
              <strong>
                {participantName(current.participant_ids)}
              </strong>

              <SongName
                versionId={current.karaoke_version_id}
                catalog={catalog}
              />
            </div>
          </button>
        ))}
      </aside>
    </div>
  )
}


export default App
