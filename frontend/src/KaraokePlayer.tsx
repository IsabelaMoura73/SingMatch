import { useEffect, useRef, useState } from 'react'
import { ExternalLink, Maximize, Minimize } from 'lucide-react'
import { api, type KaraokeVersion } from './api'
import { activeLine, lineProgress, parseLrc, type LyricLine } from './lyrics'
import { loadYouTubeApi, youtubeErrorMessage, YT_PLAYING, type YTPlayer } from './youtube'

function hideCaptions(player: YTPlayer) {
  try { player.unloadModule?.('captions') } catch { /* versão do player sem o módulo */ }
}

/**
 * Player do organizador.
 * - kind "karaoke": vídeo do YouTube que já traz a letra.
 * - kind "letra_sincronizada": vídeo original + letra LRC desenhada aqui, no
 *   tempo do player (o "vídeo de letra" é gerado na hora, sem renderizar nada).
 */
export function KaraokePlayer({ version }: { version: KaraokeVersion }) {
  const stageRef = useRef<HTMLDivElement>(null)
  const hostRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<YTPlayer | null>(null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [videoError, setVideoError] = useState('')
  const [lines, setLines] = useState<LyricLine[] | null>(null)
  const [lyricsError, setLyricsError] = useState('')
  const [offset, setOffset] = useState(0)
  const [fullscreen, setFullscreen] = useState(false)
  const synced = version.kind === 'letra_sincronizada'

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    let cancelled = false
    setVideoError(''); setTime(0); setPlaying(false)
    loadYouTubeApi().then(() => {
      if (cancelled || !window.YT) return
      const target = document.createElement('div')
      host.appendChild(target)
      playerRef.current = new window.YT.Player(target, {
        videoId: version.youtube_video_id,
        width: '100%',
        height: '100%',
        playerVars: { rel: 0, playsinline: 1, iv_load_policy: 3, cc_load_policy: 0, origin: window.location.origin },
        events: {
          // Legenda automática do YouTube duplicaria a letra; esconder quando houver LRC.
          onReady: event => { if (synced) hideCaptions(event.target) },
          onStateChange: event => {
            setPlaying(event.data === YT_PLAYING)
            if (synced && event.data === YT_PLAYING) hideCaptions(event.target)
          },
          onError: event => setVideoError(youtubeErrorMessage(event.data)),
        },
      })
    }).catch((err: Error) => { if (!cancelled) setVideoError(err.message) })
    return () => {
      cancelled = true
      try { playerRef.current?.destroy() } catch { /* player já removido */ }
      playerRef.current = null
      host.replaceChildren()
    }
  }, [version.youtube_video_id, synced])

  useEffect(() => {
    setLines(null); setLyricsError(''); setOffset(0)
    if (!synced) return
    let alive = true
    api.lyrics(version.id)
      .then(response => { if (alive) setLines(parseLrc(response.lrc)) })
      .catch((err: Error) => { if (alive) setLyricsError(err.message) })
    return () => { alive = false }
  }, [version.id, synced])

  useEffect(() => {
    if (!synced) return
    const read = () => {
      const player = playerRef.current
      if (player && typeof player.getCurrentTime === 'function') setTime(player.getCurrentTime() || 0)
    }
    if (!playing) {
      read()
      const id = window.setInterval(read, 400)  // acompanha avanços/recuos com o vídeo pausado
      return () => window.clearInterval(id)
    }
    let frame = 0
    const loop = () => { read(); frame = requestAnimationFrame(loop) }
    frame = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(frame)
  }, [synced, playing])

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === stageRef.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void stageRef.current?.requestFullscreen?.().catch(() => { /* navegador sem suporte */ })
  }

  const t = time + offset
  const index = lines ? activeLine(lines, t) : -1
  const current = lines && index >= 0 ? lines[index] : null
  const upcoming = lines ? lines.slice(index + 1, index + 3) : []
  const firstSung = lines?.find(line => line.text)
  const countdown = firstSung && t < firstSung.time && firstSung.time - t <= 5 ? Math.ceil(firstSung.time - t) : null
  const progress = lines ? lineProgress(lines, index, t) : 0

  const lyricSize = fullscreen
    ? { current: 'text-[clamp(2rem,4.4vw,4rem)]', upcoming: 'text-[clamp(1.2rem,2.4vw,2rem)]' }
    : { current: 'text-[clamp(1.35rem,2.6vw,2rem)]', upcoming: 'text-[clamp(.95rem,1.6vw,1.15rem)]' }
  const fill = `${(progress * 100).toFixed(1)}%`

  return <div ref={stageRef} className={`flex flex-col ${fullscreen ? 'h-screen w-screen gap-3 bg-background px-[3vw] py-[2vh]' : 'gap-3'}`}>
    <div className={`overflow-hidden bg-black ${fullscreen ? 'min-h-0 flex-1' : 'aspect-video'} ${synced ? 'rounded-t-2xl' : 'rounded-2xl'}`}>
      <div ref={hostRef} className="h-full w-full [&>*]:h-full [&>*]:w-full [&_iframe]:block [&_iframe]:h-full [&_iframe]:w-full [&_iframe]:border-0" />
    </div>
    {synced && (
      <div className={`-mt-3 flex flex-col justify-center gap-1.5 rounded-b-2xl border border-t-0 border-border bg-card text-center ${fullscreen ? 'min-h-[28vh] px-[4vw] py-[3vh]' : 'min-h-36 px-5 py-4'}`} aria-live="off">
        {lyricsError ? <p className="m-0 text-muted-foreground">Letra indisponível: {lyricsError}</p>
          : !lines ? <p className="m-0 text-muted-foreground">Carregando letra…</p>
          : <>
            <p
              className={`m-0 bg-clip-text leading-tight font-extrabold break-words text-transparent ${lyricSize.current}`}
              style={{ backgroundImage: `linear-gradient(90deg, var(--accent) ${fill}, var(--foreground) ${fill})` }}
            >
              {current?.text || (countdown ? `Prepare-se… ${countdown}` : '♪')}
            </p>
            {upcoming.map((line, i) => <p key={index + 1 + i} className={`m-0 leading-snug break-words text-muted-foreground ${lyricSize.upcoming}`}>{line.text || '♪'}</p>)}
          </>}
      </div>
    )}
    {videoError && (
      <p role="alert" className="m-0 flex flex-wrap items-center gap-2 rounded-xl border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-accent">
        {videoError}
        <a className="inline-flex items-center gap-1 font-semibold text-neon" href={`https://www.youtube.com/watch?v=${version.youtube_video_id}`} target="_blank" rel="noopener noreferrer">
          Abrir no YouTube <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      </p>
    )}
    <div className="flex flex-wrap items-center gap-2">
      <span className="sm-chip border border-border text-muted-foreground">{synced ? 'Letra sincronizada · voz original' : 'Vídeo de karaokê'}</span>
      {synced && lines && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground" role="group" aria-label="Sincronia da letra">
          <button type="button" className="sm-btn-ghost px-3 py-1.5 text-xs" title="Mostrar a letra mais tarde" onClick={() => setOffset(o => o - 0.5)}>− 0,5 s</button>
          <span className="tabular-nums">Sincronia {offset > 0 ? '+' : ''}{offset.toFixed(1).replace('.', ',')} s</span>
          <button type="button" className="sm-btn-ghost px-3 py-1.5 text-xs" title="Mostrar a letra mais cedo" onClick={() => setOffset(o => o + 0.5)}>+ 0,5 s</button>
        </div>
      )}
      <button type="button" className="sm-btn-ghost ml-auto px-3 py-1.5 text-xs" onClick={toggleFullscreen}>
        {fullscreen ? <Minimize className="h-3.5 w-3.5" aria-hidden="true" /> : <Maximize className="h-3.5 w-3.5" aria-hidden="true" />}
        {fullscreen ? 'Sair da tela cheia' : 'Tela cheia'}
      </button>
    </div>
  </div>
}
