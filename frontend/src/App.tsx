import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  api, type Catalog, type KaraokeVersion, type OwnProfile, type Participant, type Song,
  type PreferenceCategory, type PreferenceLabel, type Profile, type Room,
  type Script, type ScriptItem, type ScriptProposal,
} from './api'
import { KaraokePlayer } from './KaraokePlayer'

const STORAGE_KEY = 'singmatch:mvp:identity'
type Identity =
  | { role: 'host'; sessionId: string; token: string }
  | { role: 'participant'; sessionId: string; participantId: string; token: string }

type ActiveTask = 'create' | 'join' | 'interpret' | 'confirm' | 'generate' | 'save' | 'approve' | null
const CATEGORY_NAMES: Record<PreferenceCategory, string> = {
  genre: 'Gênero', artist: 'Artista', song: 'Música', tag: 'Característica',
}

function storedIdentity(): Identity | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    const data = parsed as Record<string, unknown>
    if (typeof data.sessionId !== 'string' || typeof data.token !== 'string') return null
    if (data.role === 'host') return { role: 'host', sessionId: data.sessionId, token: data.token }
    if (data.role === 'participant' && typeof data.participantId === 'string') {
      return { role: 'participant', sessionId: data.sessionId, participantId: data.participantId, token: data.token }
    }
  } catch { /* sessão antiga inválida */ }
  return null
}

function displayError(err: unknown): string {
  return err instanceof Error ? err.message : 'Ocorreu um erro inesperado. Tente novamente.'
}
function cloneProposal(script: Script): ScriptProposal {
  return { title: script.title, items: script.items.map(item => ({ ...item, participant_ids: [...item.participant_ids] })) }
}
function initials(name: string) {
  return name.trim().slice(0, 2).toUpperCase() || '♪'
}

function LabelCollection({ heading, description, labels, onChange }: {
  heading: string
  description: string
  labels: PreferenceLabel[]
  onChange: (labels: PreferenceLabel[]) => void
}) {
  const [category, setCategory] = useState<PreferenceCategory>('tag')
  const [value, setValue] = useState('')
  const add = () => {
    const cleaned = value.trim()
    if (!cleaned || cleaned.length > 150) return
    if (labels.some(item => item.category === category && item.value.toLowerCase() === cleaned.toLowerCase())) return
    onChange([...labels, { category, value: cleaned, evidence: 'Correção informada diretamente pelo participante.', origin: 'correcao_usuario' }])
    setValue('')
  }
  return (
    <section className="labels-section">
      <div className="section-intro"><strong>{heading}</strong><span>{description}</span></div>
      <div className="label-list">
        {labels.length === 0 && <p className="muted smaller">Nenhuma informação nesta categoria.</p>}
        {labels.map((label, index) => (
          <div className="label-card" key={`${label.category}-${label.value}-${index}`}>
            <div className="label-content">
              <span className="chip light">{CATEGORY_NAMES[label.category]}</span>
              <strong>{label.value}</strong>
              <small>{label.origin === 'texto' ? `Evidência: “${label.evidence}”` : 'Adicionada por você'}</small>
            </div>
            <button type="button" className="icon-btn" onClick={() => onChange(labels.filter((_, i) => i !== index))} aria-label={`Remover ${label.value}`} title="Remover informação">×</button>
          </div>
        ))}
      </div>
      <div className="add-label">
        <select aria-label={`Categoria para adicionar em ${heading}`} value={category} onChange={e => setCategory(e.target.value as PreferenceCategory)}>
          {Object.entries(CATEGORY_NAMES).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
        </select>
        <input value={value} maxLength={150} onChange={e => setValue(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }} placeholder="Adicionar correção..." aria-label={`Valor para adicionar em ${heading}`} />
        <button type="button" className="btn subtle small" onClick={add} disabled={!value.trim()}>Adicionar</button>
      </div>
    </section>
  )
}

function ProfileReview({ profile, onChange }: { profile: Profile; onChange: (profile: Profile) => void }) {
  return (
    <div className="review-panel">
      <div className="eyebrow">Perfil interpretado pela IA · revisável</div>
      <h3>Confira antes de confirmar</h3>
      <p className="muted">As informações a seguir foram extraídas do seu texto. Remova interpretações incorretas e adicione correções.</p>
      <div className="review-grid">
        <LabelCollection heading="Gosto de" description="Preferências que ajudam a escolher músicas" labels={profile.likes} onChange={likes => onChange({ ...profile, likes })} />
        <LabelCollection heading="Não quero" description="Vetos que o roteiro deve respeitar" labels={profile.vetoes} onChange={vetoes => onChange({ ...profile, vetoes })} />
      </div>
      <div className="form-grid two">
        <label className="field">Formato preferido
          <select value={profile.preferred_format} onChange={e => onChange({ ...profile, preferred_format: e.target.value as Profile['preferred_format'] })}>
            <option value="indiferente">Indiferente</option><option value="solo">Solo</option><option value="dueto">Dueto</option>
          </select>
        </label>
        <label className="field">Permite duetos?
          <select value={profile.duet_allowed === null ? 'unknown' : String(profile.duet_allowed)} onChange={e => onChange({ ...profile, duet_allowed: e.target.value === 'unknown' ? null : e.target.value === 'true' })}>
            <option value="unknown">Não informado</option><option value="true">Sim</option><option value="false">Não</option>
          </select>
        </label>
      </div>
      {!!profile.questions.length && <div className="notice"><strong>Questões sinalizadas pela IA</strong><ul>{profile.questions.map((q, i) => <li key={i}>{q}</li>)}</ul></div>}
      <p className="muted smaller">Neste piloto, o roteiro é exclusivamente solo, mesmo se você permitir duetos.</p>
    </div>
  )
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
  const [mode, setMode] = useState<'create' | 'join'>('create')
  const [intention, setIntention] = useState('Começar tranquilo e terminar animado')
  const [joinCode, setJoinCode] = useState(new URLSearchParams(window.location.search).get('code')?.toUpperCase() || '')
  const [joinName, setJoinName] = useState('')
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
    const data = await api.room(target.sessionId, target.token)
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
      api.room(identity.sessionId, identity.token)
        .then(data => { if (alive) { setRoom(data); setConnected(true) } })
        .catch(() => { if (alive) setConnected(false) })
    }
    poll()
    const timer = window.setInterval(poll, 7000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [identity])

  useEffect(() => {
    if (!identity || identity.role !== 'participant') return
    let alive = true
    api.ownProfile(identity.participantId, identity.token).then(profile => {
      if (!alive) return
      setOwn(profile)
      setRawText(profile.text || '')
      setInterpretedText(profile.text || '')
      setDraft(profile.confirmed || profile.draft)
    }).catch(err => { if (alive) setError(displayError(err)) })
    return () => { alive = false }
  }, [identity])

  const execute = async (task: NonNullable<ActiveTask>, fn: () => Promise<void>) => {
    setPending(task)
    setError('')
    setMessage('')
    try { await fn() }
    catch (err) { setError(displayError(err)) }
    finally { setPending(null) }
  }

  const createRoom = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await execute('create', async () => {
      const result = await api.create(intention.trim())
      saveIdentity({ role: 'host', sessionId: result.session.id, token: result.host_token })
    })
  }
  const joinRoom = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await execute('join', async () => {
      const data = await api.join(joinCode.trim().toUpperCase(), joinName.trim())
      saveIdentity({ role: 'participant', sessionId: data.session_id, participantId: data.participant_id, token: data.participant_token })
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
    if (!identity || identity.role !== 'participant') return
    const person = identity
    await execute('interpret', async () => {
      const result = await api.interpret(person.participantId, person.token, rawText.trim())
      setDraft(result.draft)
      setInterpretedText(rawText.trim())
      setOwn(old => old ? { ...old, text: rawText.trim(), draft: result.draft, confirmed: null } : null)
      await refresh(person)
      setMessage('Perfil interpretado. Revise e confirme abaixo.')
    })
  }
  const confirm = async () => {
    if (!identity || identity.role !== 'participant' || !draft) return
    const person = identity
    if (rawText.trim() !== interpretedText) { setError('O texto mudou. Clique em “Interpretar com IA” novamente antes de confirmar.'); return }
    await execute('confirm', async () => {
      const result = await api.confirm(person.participantId, person.token, draft)
      setOwn(result)
      setDraft(result.confirmed)
      await refresh(person)
      setMessage('Preferências confirmadas! Você já pode aguardar o roteiro.')
    })
  }
  const generate = async () => {
    if (!identity || identity.role !== 'host') return
    if (room?.script?.approved && !window.confirm('Gerar outro roteiro invalidará a aprovação atual. Continuar?')) return
    const host = identity
    await execute('generate', async () => {
      await api.generate(host.sessionId, host.token)
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
    if (!identity || identity.role !== 'host' || !proposal || editVersion === null) return
    if (new Set(proposal.items.map(i => i.karaoke_version_id)).size !== proposal.items.length) {
      setError('Uma música não pode se repetir no roteiro. Escolha vídeos diferentes.'); return
    }
    const host = identity
    await execute('save', async () => {
      await api.edit(host.sessionId, host.token, editVersion, proposal)
      await refresh(host)
      setEditing(false); setPlayingIndex(null)
      setMessage('Nova versão do roteiro salva. Aprove-a para reproduzir.')
    })
  }
  const approve = async () => {
    if (!identity || identity.role !== 'host' || !room?.script) return
    const host = identity
    await execute('approve', async () => {
      await api.approve(host.sessionId, host.token, room.script!.version)
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
  const participantName = (ids: string[]) => ids.map(id => room?.participants.find(p => p.id === id)?.name || 'Participante').join(' + ')

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand"><span className="brand-disc">♪</span><span>Sing<span className="brand-accent">Match</span></span></div>
          <span className="topbar-note">KARAOKÊ CRIADO EM CONJUNTO</span>
          {identity && <button type="button" className="nav-exit" onClick={exitRoom}>Sair deste dispositivo ↗</button>}
        </div>
      </header>

      <main className="main-container">
        {!identity ? (
          <div className="home-layout">
            <div className="hero">
              <div className="eyebrow"><span className="eyebrow-rule"/> SUA NOITE, SEU REPERTÓRIO</div>
              <h1>Todo mundo<br/>entra no <em>ritmo.</em></h1>
              <p className="hero-copy">Reúna seus amigos, conte seus gostos musicais e deixe a IA propor uma noite de karaokê com a cara do grupo.</p>
              <div className="hero-art" aria-hidden="true"><div className="vinyl"><div className="vinyl-label">SM<span>♫</span></div></div><div className="music-doodle">♫</div></div>
              <div className="hero-foot"><span>01 · ENTRAR</span><span>02 · CRIAR JUNTOS</span><span>03 · CANTAR</span></div>
            </div>
            <section className="entry-card" aria-label="Acessar SingMatch">
              <div className="segmented">
                <button type="button" className={mode === 'create' ? 'active' : ''} onClick={() => setMode('create')}>Criar sala</button>
                <button type="button" className={mode === 'join' ? 'active' : ''} onClick={() => setMode('join')}>Entrar com código</button>
              </div>
              {mode === 'create' ? <form onSubmit={createRoom} className="entry-form">
                <span className="eyebrow">PARA O ORGANIZADOR</span>
                <h2>Comece a noite</h2>
                <p className="muted">Crie um espaço para seu grupo. Os amigos entram usando um código.</p>
                <label className="field">Gênero musical <select disabled value="forro"><option value="forro">Forró · piloto</option></select></label>
                <label className="field">Qual é a intenção da noite?
                  <textarea value={intention} maxLength={500} rows={4} onChange={e => setIntention(e.target.value)} placeholder="Ex.: começar tranquilo e terminar animado"/>
                </label>
                <button className="btn primary full" disabled={pending !== null}>{pending === 'create' ? 'Criando sala...' : 'Criar minha sala →'}</button>
                <p className="form-foot">O organizador controla o roteiro e o player. Sem cadastro.</p>
              </form> : <form onSubmit={joinRoom} className="entry-form">
                <span className="eyebrow">PARA OS PARTICIPANTES</span>
                <h2>Entre na roda</h2>
                <p className="muted">Peça o código ao organizador. Depois, conte o que você gosta de cantar.</p>
                <label className="field">Código da sala
                  <input required maxLength={8} className="code-input" value={joinCode} onChange={e => setJoinCode(e.target.value.toUpperCase())} placeholder="AB12CD34"/>
                </label>
                <label className="field">Seu nome
                  <input required maxLength={80} value={joinName} onChange={e => setJoinName(e.target.value)} placeholder="Como vamos chamar você?"/>
                </label>
                <button className="btn primary full" disabled={pending !== null || !joinCode.trim() || !joinName.trim()}>{pending === 'join' ? 'Entrando...' : 'Entrar na sala →'}</button>
                <p className="form-foot">Cada pessoa tem seu próprio acesso e confirma suas preferências.</p>
              </form>}
            </section>
          </div>
        ) : (
          <div className="room-layout">
            <div className="room-header">
              <div>
                <span className="eyebrow">{identity.role === 'host' ? 'PAINEL DO ORGANIZADOR' : 'MEU ESPAÇO NO KARAOKÊ'}</span>
                <h1>{identity.role === 'host' ? 'A noite é nossa.' : 'Sua voz faz parte.'}</h1>
                <p className="muted">Forró · {room?.session.intention || 'Uma noite de música criada em grupo'}</p>
              </div>
              <div className="code-panel"><span>CÓDIGO DA SALA</span><strong>{room?.session.code || '········'}</strong>{identity.role === 'host' && <button type="button" onClick={copyCode} className="text-button">Copiar código ↗</button>}</div>
            </div>
            {!connected && <div className="alert error" role="alert">Conexão com a API indisponível. Tentando reconectar...</div>}
            {!room ? <div className="paper-card">Carregando informações da sala...</div> : <>
              <section className="paper-card participants-card">
                <div className="card-title-row"><div><span className="eyebrow">QUEM ESTÁ NA RODA</span><h2>Participantes <span className="title-count">({room.participants.length})</span></h2></div><button className="btn outline small" type="button" onClick={() => { void refresh(identity).catch(err => setError(displayError(err))) }}>↻ Atualizar</button></div>
                {room.participants.length ? <div className="people-grid">{room.participants.map((person: Participant) => <div className="person-card" key={person.id}><div className="avatar">{initials(person.name)}</div><div className="person-info"><strong>{person.name}</strong><span className={person.profile_confirmed ? 'ready' : 'waiting'}>{person.profile_confirmed ? '✓ Perfil confirmado' : 'Aguardando perfil'}</span></div></div>)}</div> : <div className="empty-state">Ninguém entrou ainda. Compartilhe o código da sala.</div>}
                <div className="status-line"><span>Atualização automática a cada 7 segundos</span><span>{room.participants.filter(p => p.profile_confirmed).length}/{room.participants.length} perfis prontos</span></div>
              </section>

              {identity.role === 'participant' ? <section className="paper-card profile-card">
                <span className="eyebrow">01 · PREFERÊNCIAS</span>
                <h2>O que você gosta de cantar?</h2>
                <p className="muted">Escreva de um jeito natural. A IA transforma sua resposta em preferências e restrições, mas você decide o que confirmar.</p>
                <form onSubmit={interpret} className="profile-form">
                  <label className="field">Conte seus gostos musicais
                    <textarea rows={5} minLength={3} maxLength={2000} required value={rawText} onChange={e => setRawText(e.target.value)} placeholder="Ex.: Gosto de forró animado, mas não quero músicas românticas. Prefiro cantar sozinho."/>
                  </label>
                  <div className="inline-actions"><button className="btn secondary" disabled={pending !== null || rawText.trim().length < 3}>{pending === 'interpret' ? 'Interpretando com IA...' : own?.draft ? 'Interpretar novamente ✧' : 'Interpretar com IA ✧'}</button><span className="muted smaller">Sua resposta pode ser processada pela API OpenAI.</span></div>
                </form>
                {draft && <div className="profile-revision">
                  <ProfileReview profile={draft} onChange={setDraft} />
                  {rawText.trim() !== interpretedText && <div className="notice warn">Você alterou o texto. Interprete novamente antes de confirmar o perfil.</div>}
                  <div className="profile-footer"><button type="button" className="btn primary" disabled={pending !== null || rawText.trim() !== interpretedText} onClick={confirm}>{pending === 'confirm' ? 'Salvando...' : own?.confirmed ? 'Salvar correções do perfil ✓' : 'Confirmar meu perfil ✓'}</button>{own?.confirmed && <span className="confirmed-mark">✓ Seu perfil já foi confirmado. Alterações exigem nova confirmação.</span>}</div>
                </div>}
                {room.script && <div className="participant-script"><span className="eyebrow">02 · ROTEIRO DA NOITE</span><h3>{room.script.title}</h3><p className="muted">{room.script.approved ? 'O organizador aprovou este roteiro.' : 'Esta ainda é uma proposta. O organizador pode editá-la.'}</p><ol>{room.script.items.map(item => <li key={item.position}><b>{participantName(item.participant_ids)}</b> — <SongName versionId={item.karaoke_version_id} catalog={catalog}/></li>)}</ol><div className="notice">O player fica disponível apenas no dispositivo do organizador.</div></div>}
              </section> : <section className="paper-card script-card">
                <div className="card-title-row"><div><span className="eyebrow">02 · COMPOSIÇÃO COLETIVA</span><h2>Roteiro da noite</h2></div>{room.script && <span className={`state-tag ${room.script.approved ? 'done' : ''}`}>{room.script.approved ? '✓ Aprovado' : '✧ Proposta · v' + room.script.version}</span>}</div>
                {!room.participants.length ? <div className="notice">Compartilhe o código e aguarde seus amigos entrarem.</div> : !room.participants.every(p => p.profile_confirmed) ? <div className="notice">Aguardando a confirmação das preferências de todos os participantes antes de gerar o roteiro.</div> : <div className="inline-actions"><button type="button" className="btn secondary" onClick={generate} disabled={pending !== null || editing}>{pending === 'generate' ? 'Criando roteiro...' : room.script ? '✧ Gerar outro roteiro' : '✧ Gerar roteiro com IA'}</button><span className="muted smaller">Gera uma apresentação solo por pessoa usando músicas aprovadas do catálogo.</span></div>}
                {room.script && <div className="script-area">
                  {editing && proposal ? <>
                    <div className="edit-banner"><strong>Modo de edição</strong><span>Troque músicas ou altere a ordem. Nenhuma pessoa pode ser removida da rodada.</span></div>
                    {editVersion !== room.script.version && <div className="alert error">Outra versão foi salva. Cancele a edição e atualize a sala antes de continuar.</div>}
                    <label className="field">Título do roteiro<input maxLength={160} required value={proposal.title} onChange={e => setProposal(old => old ? {...old, title: e.target.value } : old)}/></label>
                    <div className="script-list">{proposal.items.map((item, i) => <div className="script-item" key={item.participant_ids.join('-')}>
                      <div className="script-pos">{i+1}</div><div className="script-details"><span className="item-person">{participantName(item.participant_ids)}</span><label className="field"><span>Música para esta apresentação</span><select value={item.karaoke_version_id} onChange={e => changeItem(i, {karaoke_version_id: e.target.value})}>{eligibleVideos.map(video => <option key={video.id} value={video.id}>{songsById.get(video.song_id)?.title || video.id} — {songsById.get(video.song_id)?.artists.join(', ')}{video.kind === 'letra_sincronizada' ? ' (letra na tela)' : ' (karaokê)'}</option>)}</select></label></div>
                      <div className="order-actions"><button className="icon-btn" type="button" aria-label={`Subir apresentação de ${participantName(item.participant_ids)}`} onClick={() => moveItem(i, -1)} disabled={i === 0}>↑</button><button className="icon-btn" type="button" aria-label={`Descer apresentação de ${participantName(item.participant_ids)}`} onClick={() => moveItem(i, 1)} disabled={i === proposal.items.length-1}>↓</button></div>
                    </div>)}</div>
                    <div className="inline-actions"><button type="button" className="btn primary" disabled={pending !== null || editVersion !== room.script.version || !proposal.title.trim()} onClick={saveEdit}>{pending === 'save' ? 'Salvando...' : 'Salvar alterações ✓'}</button><button type="button" className="btn outline" onClick={() => { setEditing(false); setProposal(null) }}>Cancelar</button></div>
                    <p className="muted smaller">O backend valida vetos e impedirá vídeos repetidos ou incompatíveis antes de salvar.</p>
                  </> : <>
                    <h3 className="script-title">{room.script.title}</h3><div className="script-list">{room.script.items.map(item => <div className="script-item" key={item.position}>
                      <div className="script-pos">{item.position}</div><div className="script-details"><span className="item-person">{participantName(item.participant_ids)}</span><SongName versionId={item.karaoke_version_id} catalog={catalog}/><p className="reason">{item.justification || (item.origin === 'manual' ? 'Escolha editada pelo organizador.' : 'Apresentação sugerida.')}</p></div><span className="chip light">{item.origin === 'ia' ? '✧ IA' : 'Manual'}</span>
                    </div>)}</div>
                    <div className="inline-actions"><button type="button" className="btn outline" disabled={pending !== null} onClick={() => startEdit(room.script!)}>Editar roteiro</button>{!room.script.approved && <button type="button" className="btn primary" disabled={pending !== null || room.script.input_revision !== room.session.revision} onClick={approve}>{pending === 'approve' ? 'Aprovando...' : 'Aprovar roteiro ✓'}</button>}</div>
                    {room.script.input_revision !== room.session.revision && <div className="notice warn">Os perfis mudaram desde esta proposta. Gere um novo roteiro antes de aprovar.</div>}
                  </>}
                </div>}
              </section>}

              {identity.role === 'host' && room.script?.approved && room.script.input_revision === room.session.revision && !editing && <section className="paper-card player-card"><div className="card-title-row"><div><span className="eyebrow">03 · HORA DE CANTAR</span><h2>Player do organizador</h2></div><span className="state-tag done">Repertório aprovado</span></div><p className="muted">Reproduza na ordem do roteiro. Músicas com letra sincronizada mostram a letra abaixo do vídeo; use “Tela cheia” na TV ou projetor. O player aparece apenas aqui, no dispositivo do organizador.</p>
                {playingIndex === null ? <button className="btn primary" type="button" onClick={() => setPlayingIndex(0)}>▶ Abrir o player</button> : <Player script={room.script} index={playingIndex} versions={versionsById} catalog={catalog} participantName={participantName} onSelect={setPlayingIndex}/>}
                <p className="muted smaller">Vídeos incorporados via YouTube. A disponibilidade e permissões de reprodução podem mudar; a aprovação do piloto não equivale a revisão de direitos.</p>
              </section>}
            </>}
          </div>
        )}
        {error && <div className="feedback error" role="alert"><strong>Não foi possível concluir</strong><span>{error}</span><button type="button" onClick={() => setError('')} aria-label="Fechar erro">×</button></div>}
        {message && <div className="feedback success" role="status"><span>{message}</span><button type="button" onClick={() => setMessage('')} aria-label="Fechar aviso">×</button></div>}
      </main>
      <footer className="footer"><span>SINGMATCH · PROJETO FERRAMENTA</span><span>Forró · Piloto colaborativo · 2026</span></footer>
    </div>
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
