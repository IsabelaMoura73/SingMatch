/** Contratos HTTP compatíveis com backend/app/routes.py da Etapa 4. */
export type PreferenceCategory = 'genre' | 'artist' | 'song' | 'tag'
export type PreferenceLabel = {
  category: PreferenceCategory
  value: string
  evidence: string
  origin: 'texto' | 'correcao_usuario'
}
export type Profile = {
  likes: PreferenceLabel[]
  vetoes: PreferenceLabel[]
  preferred_format: 'solo' | 'dueto' | 'indiferente'
  duet_allowed: boolean | null
  questions: string[]
}
export type Session = {
  id: string
  code: string
  genre: string
  intention: string
  status: 'lobby' | 'ready' | 'playing' | 'finished'
  revision: number
}
export type Participant = { id: string; name: string; profile_confirmed: boolean }
export type ScriptItem = {
  position: number
  karaoke_version_id: string
  participant_ids: string[]
  justification: string | null
  origin: 'ia' | 'manual'
}
export type ScriptProposal = { title: string; items: ScriptItem[] }
export type Script = ScriptProposal & {
  session_id: string
  version: number
  input_revision: number
  approved: boolean
}
export type Room = { session: Session; participants: Participant[]; script: Script | null }
export type Song = {
  id: string; title: string; artists: string[]; genre: string
  mood: string | null; energy: number | null; duet_possible: boolean
}
export type KaraokeVersion = {
  id: string; song_id: string; youtube_video_id: string; approved: boolean
  rights_reviewed: boolean; verified_at: string | null
}
export type Catalog = { songs: Song[]; karaoke_versions: KaraokeVersion[] }
export type OwnProfile = {
  id: string; name: string; text: string | null
  draft: Profile | null; confirmed: Profile | null
}

async function request<T>(url: string, options: RequestInit = {}, token?: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new Error('Não foi possível conectar à API. Confira se o FastAPI está rodando na porta 8000.')
  }
  if (!response.ok) {
    let message = `Erro HTTP ${response.status}`
    try {
      const body = await response.json() as { detail?: string | { msg?: string }[] }
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map(x => x.msg || 'Campo inválido').join('; ')
    } catch { /* Resposta sem JSON */ }
    if (response.status === 409) message += ' Atualize a sala ou revise sua escolha.'
    throw new Error(message)
  }
  return await response.json() as T
}

const json = (value: unknown) => JSON.stringify(value)
export const api = {
  health: () => request<{status: string}>('/api/health'),
  catalog: () => request<Catalog>('/api/catalog?genre=forro'),
  create: (intention: string) => request<{session: Session; host_token: string}>('/api/sessions', {
    method: 'POST', body: json({ genre: 'forro', intention }),
  }),
  join: (code: string, name: string) => request<{session_id: string; participant_id: string; participant_token: string}>('/api/join', {
    method: 'POST', body: json({ code, name }),
  }),
  room: (id: string, token: string) => request<Room>(`/api/sessions/${encodeURIComponent(id)}`, {}, token),
  ownProfile: (id: string, token: string) => request<OwnProfile>(`/api/participants/${encodeURIComponent(id)}/profile`, {}, token),
  interpret: (id: string, token: string, text: string) => request<{draft: Profile}>(`/api/participants/${encodeURIComponent(id)}/interpret`, {
    method: 'POST', body: json({text}),
  }, token),
  confirm: (id: string, token: string, profile: Profile) => request<OwnProfile>(`/api/participants/${encodeURIComponent(id)}/profile`, {
    method: 'PUT', body: json({profile}),
  }, token),
  generate: (id: string, token: string) => request<{script: Script}>(`/api/sessions/${encodeURIComponent(id)}/script`, {
    method: 'POST',
  }, token),
  edit: (id: string, token: string, expected_version: number, proposal: ScriptProposal) => request<{script: Script}>(`/api/sessions/${encodeURIComponent(id)}/script`, {
    method: 'PUT', body: json({expected_version, proposal}),
  }, token),
  approve: (id: string, token: string, expected_version: number) => request<{script: Script}>(`/api/sessions/${encodeURIComponent(id)}/script/approve`, {
    method: 'POST', body: json({expected_version}),
  }, token),
}
