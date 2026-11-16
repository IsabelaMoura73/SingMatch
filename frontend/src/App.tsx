import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { ArrowLeft, Play } from 'lucide-react'
import {
  api, type Catalog, type KaraokeVersion, type OwnProfile, type Song,
  type Profile, type Room,
  type Script, type ScriptItem, type ScriptProposal,
} from './api'
import { Shell } from './components/Shell'
import { Home } from './components/Home'
import { PreferencesScreen, ReviewScreen } from './components/Profile'
import { Steps, type Screen } from './components/Steps'
import { PlayerCard } from './components/Player'
import { Toast } from './components/Toast'
import { HostScriptCard, LobbyActions, ParticipantScriptCard, ParticipantsCard, RoomHeader, type SongLookup } from './components/Room'

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

const SCREENS: Screen[] = ['preferencias', 'perfil', 'sala', 'roteiro', 'player']
type Page = Screen | 'inicio'
/** Tela pedida no endereço (#sala, #roteiro...), para o "voltar" do navegador e o F5 funcionarem. */
function screenFromHash(): Page | null {
  const hash = window.location.hash.slice(1)
  if (hash === 'inicio') return 'inicio'
  return (SCREENS as string[]).includes(hash) ? hash as Screen : null
}

function displayError(err: unknown): string {
  return err instanceof Error ? err.message : 'Ocorreu um erro inesperado. Tente novamente.'
}
function cloneProposal(script: Script): ScriptProposal {
  return { title: script.title, items: script.items.map(item => ({ ...item, participant_ids: [...item.participant_ids] })) }
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
  const [requestedScreen, setRequestedScreen] = useState<Page | null>(screenFromHash)
  const atHome = requestedScreen === 'inicio'
  const [ownLoaded, setOwnLoaded] = useState(false)

  useEffect(() => {
    const onHashChange = () => setRequestedScreen(screenFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])
  const go = (screen: Page) => {
    setRequestedScreen(screen)
    if (window.location.hash !== `#${screen}`) window.location.hash = screen
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
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
    setRequestedScreen(null)
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
    setOwnLoaded(false)
    api.ownProfile(me.id, me.token).then(profile => {
      if (!alive) return
      setOwnLoaded(true)
      setOwn(profile)
      setRawText(profile.text || '')
      setInterpretedText(profile.text || '')
      setDraft(profile.confirmed || profile.draft)
    }).catch(err => { if (alive) { setOwnLoaded(true); setError(displayError(err)) } })
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
      // Preserva o acesso à sala mesmo se a aba recarregar durante o /join.
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(created))
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
      go('preferencias')
    })
  }
  const goHome = () => {
    go('inicio')
  }
  const exitRoom = () => {
    if (!window.confirm('Sair apaga deste navegador o acesso à sala. Sem o token, não será possível recuperar o papel de organizador ou este participante. Deseja sair?')) return
    sessionStorage.removeItem(STORAGE_KEY)
    setIdentity(null); setRoom(null); setOwn(null); setDraft(null)
    setPlayingIndex(null); setEditing(false); setError(''); setMessage('')
    setRequestedScreen(null)
    window.history.replaceState(null, '', window.location.pathname)
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
      go('perfil')
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
      go('sala')
      setMessage('Perfil confirmado! Agora é esperar o roteiro.')
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
      go('roteiro')
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
      setPlayingIndex(null)
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
  const script = room?.script ?? null
  const stale = !!script && !!room && script.input_revision !== room.session.revision
  const canPlay = isHost && !!script?.approved && !stale && !editing
  const available = (screen: Screen) =>
    screen === 'preferencias' ? !!me
      : screen === 'perfil' ? !!me && !!draft
        : screen === 'sala' ? true
          : screen === 'roteiro' ? !!script
            : canPlay
  const defaultScreen: Screen = me && !own?.confirmed ? (draft ? 'perfil' : 'preferencias') : script ? 'roteiro' : 'sala'
  const screen = requestedScreen && requestedScreen !== 'inicio' && available(requestedScreen) ? requestedScreen : defaultScreen
  useEffect(() => {
    if (!identity || !room || (me && !ownLoaded) || requestedScreen !== null) return
    // Fixa a primeira etapa no histórico antes que a confirmação mude a tela padrão.
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${defaultScreen}`)
    setRequestedScreen(defaultScreen)
  }, [identity, room, me, ownLoaded, requestedScreen, defaultScreen])
  const stepScreens = SCREENS.filter(s => (s === 'preferencias' || s === 'perfil') ? !!me : s === 'player' ? isHost : true)
  const myName = room?.participants.find(p => p.id === me?.id)?.name || own?.name || ''
  const allReady = !!room && room.participants.length > 0 && room.participants.every(p => p.profile_confirmed)
  const participantName = (ids: string[]) => ids.map(id => room?.participants.find(p => p.id === id)?.name || 'Participante').join(' + ')

  return (
    <Shell code={identity && !atHome ? room?.session.code : undefined} onExit={identity ? exitRoom : undefined} onHome={goHome}>

      <main className="mx-auto w-full max-w-[1210px] px-4 pt-2 pb-16 sm:px-7">
        {!identity || atHome ? (
          <>
          {identity && (
            <div className="mx-auto mt-2 max-w-3xl px-1">
              <div className="sm-card flex flex-col gap-3 border-primary/40 sm:flex-row sm:items-center">
                <div className="flex-1">
                  <p className="m-0 font-semibold">Você tem uma sala aberta{room ? <> · <span className="font-mono tracking-widest text-accent">{room.session.code}</span></> : null}</p>
                  <p className="m-0 text-sm text-muted-foreground">Criar ou entrar em outra sala substitui o acesso a esta neste dispositivo.</p>
                </div>
                <button type="button" className="sm-btn-primary shrink-0" onClick={() => go(screen)}>Voltar para a sala</button>
              </div>
            </div>
          )}
          <Home
            busy={pending !== null}
            creating={pending === 'create'}
            joining={pending === 'join'}
            initialCode={initialCode}
            onCreate={(intention, hostName) => { void createRoom(intention, hostName) }}
            onJoin={(code, name) => { void joinRoom(code, name) }}
          />
          </>
        ) : (
          <div className="flex flex-col gap-5">
            {!connected && <p role="alert" className="mb-0 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">Conexão com a API indisponível. Tentando reconectar...</p>}
            {!room || (me && !ownLoaded) ? <div className="sm-card text-muted-foreground">Carregando informações da sala...</div> : <>
              <Steps screens={stepScreens} current={screen} available={available} onSelect={go} />

              {screen === 'preferencias' && me && (
                <PreferencesScreen
                  name={myName} intention={room.session.intention} own={own}
                  rawText={rawText} interpretedText={interpretedText} draft={draft}
                  busy={pending !== null} interpreting={pending === 'interpret'}
                  onTextChange={setRawText} onInterpret={interpret} onReview={() => go('perfil')}
                />
              )}

              {screen === 'perfil' && me && draft && (
                <ReviewScreen
                  name={myName} intention={room.session.intention} own={own}
                  rawText={rawText} interpretedText={interpretedText} draft={draft}
                  busy={pending !== null} tagSuggestions={tagSuggestions} confirming={pending === 'confirm'}
                  onDraftChange={setDraft} onConfirm={() => { void confirm() }} onRewrite={() => go('preferencias')}
                />
              )}

              {screen === 'sala' && <>
                <RoomHeader isHost={isHost} intention={room.session.intention} code={room.session.code} onCopy={() => { void copyCode() }} />
                {isHost && !me && !['playing', 'finished'].includes(room.session.status) && (
                  <form onSubmit={joinAsHost} className="sm-card flex flex-col gap-3 sm:flex-row sm:items-center">
                    <div className="flex-1">
                      <p className="mb-0 font-semibold">Vai cantar também?</p>
                      <p className="mb-0 text-sm text-muted-foreground">Entre na roda com seu nome. Você ganha uma música no roteiro, como os amigos.</p>
                    </div>
                    <input className="sm-input sm:max-w-56" aria-label="Seu nome" placeholder="Seu nome" maxLength={80} required value={hostJoinName} onChange={e => setHostJoinName(e.target.value)} />
                    <button className="sm-btn-primary shrink-0" disabled={pending !== null || !hostJoinName.trim()}>{pending === 'join-host' ? 'Entrando...' : 'Entrar também como participante'}</button>
                  </form>
                )}
                <ParticipantsCard participants={room.participants} meId={me?.id} hostParticipantId={isHost ? me?.id : undefined} onRefresh={() => { void refresh(identity).catch(err => setError(displayError(err))) }} />
                <LobbyActions
                  isHost={isHost} singing={!!me} profileConfirmed={!!own?.confirmed} hasScript={!!script} allReady={allReady}
                  generating={pending === 'generate'} busy={pending !== null}
                  onProfile={() => go(own?.confirmed ? 'perfil' : draft ? 'perfil' : 'preferencias')}
                  onGenerate={() => { void generate() }}
                  onScript={() => go('roteiro')}
                />
              </>}

              {screen === 'roteiro' && script && (isHost ? <>
                <HostScriptCard
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
                  onStartEdit={() => startEdit(script)}
                  onCancelEdit={() => { setEditing(false); setProposal(null) }}
                  onSaveEdit={() => { void saveEdit() }}
                  onApprove={() => { void approve() }}
                  onTitleChange={title => setProposal(old => old ? { ...old, title } : old)}
                  onChangeItem={changeItem}
                  onMoveItem={moveItem}
                />
                {canPlay && (
                  <button type="button" className="sm-btn-primary px-6 py-3 text-base" onClick={() => go('player')}>
                    <Play className="h-5 w-5" aria-hidden="true" />Abrir o player
                  </button>
                )}
              </> : <ParticipantScriptCard script={script} participantName={participantName} lookup={lookup} />)}

              {screen === 'player' && script && <>
                <button type="button" className="sm-btn-ghost self-start" onClick={() => go('roteiro')}>
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />Voltar ao roteiro
                </button>
                <PlayerCard script={script} index={playingIndex ?? 0} lookup={lookup} participantName={participantName} onSelect={setPlayingIndex} />
              </>}
            </>}
          </div>
        )}
        {error && <Toast tone="error" title="Não foi possível concluir" message={error} onClose={() => setError('')} />}
        {message && !error && <Toast tone="success" message={message} onClose={() => setMessage('')} />}
      </main>
    </Shell>
  )
}


export default App
