import { useEffect, useRef, useState, type CSSProperties } from 'react'
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

  return <div ref={stageRef} className={`karaoke-stage${synced ? ' synced' : ''}${fullscreen ? ' is-fullscreen' : ''}`}>
    <div className="video-frame"><div className="yt-host" ref={hostRef} /></div>
    {synced && <div className="lyrics-panel">
      {lyricsError ? <p className="lyrics-status">Letra indisponível: {lyricsError}</p>
        : !lines ? <p className="lyrics-status">Carregando letra…</p>
        : <>
          <p className="lyric-line current" style={{ '--progress': `${(progress * 100).toFixed(1)}%` } as CSSProperties}>
            {current?.text || (countdown ? `Prepare-se… ${countdown}` : '♪')}
          </p>
          {upcoming.map((line, i) => <p key={index + 1 + i} className="lyric-line upcoming">{line.text || '♪'}</p>)}
        </>}
    </div>}
    {videoError && <div className="notice warn video-error">{videoError} <a href={`https://www.youtube.com/watch?v=${version.youtube_video_id}`} target="_blank" rel="noopener noreferrer">Abrir no YouTube ↗</a></div>}
    <div className="stage-controls">
      <span className="chip light">{synced ? 'Letra sincronizada · voz original' : 'Vídeo de karaokê'}</span>
      {synced && lines && <div className="offset-control" role="group" aria-label="Sincronia da letra">
        <button type="button" className="btn small outline" title="Mostrar a letra mais tarde" onClick={() => setOffset(o => o - 0.5)}>− 0,5 s</button>
        <span>Sincronia {offset > 0 ? '+' : ''}{offset.toFixed(1).replace('.', ',')} s</span>
        <button type="button" className="btn small outline" title="Mostrar a letra mais cedo" onClick={() => setOffset(o => o + 0.5)}>+ 0,5 s</button>
      </div>}
      <button type="button" className="btn small outline" onClick={toggleFullscreen}>{fullscreen ? 'Sair da tela cheia' : '⛶ Tela cheia'}</button>
    </div>
  </div>
}
