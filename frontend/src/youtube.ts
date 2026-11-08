/** Carregamento único da YouTube IFrame Player API, com tipos mínimos. */
export type YTPlayer = {
  getCurrentTime(): number
  getPlayerState(): number
  playVideo(): void
  pauseVideo(): void
  seekTo(seconds: number, allowSeekAhead: boolean): void
  destroy(): void
  /** Não documentado, mas estável: unloadModule('captions') esconde as legendas automáticas. */
  unloadModule?(name: string): void
}

type YTEvent = { data: number; target: YTPlayer }
export type YTPlayerOptions = {
  videoId: string
  width?: string | number
  height?: string | number
  playerVars?: Record<string, string | number>
  events?: {
    onReady?: (event: YTEvent) => void
    onStateChange?: (event: YTEvent) => void
    onError?: (event: YTEvent) => void
  }
}

declare global {
  interface Window {
    YT?: { Player: new (element: HTMLElement, options: YTPlayerOptions) => YTPlayer }
    onYouTubeIframeAPIReady?: () => void
  }
}

export const YT_PLAYING = 1

let loading: Promise<void> | null = null

export function loadYouTubeApi(): Promise<void> {
  if (window.YT?.Player) return Promise.resolve()
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const previous = window.onYouTubeIframeAPIReady
      window.onYouTubeIframeAPIReady = () => { previous?.(); resolve() }
      const script = document.createElement('script')
      script.src = 'https://www.youtube.com/iframe_api'
      script.async = true
      script.onerror = () => { loading = null; reject(new Error('Não foi possível carregar o player do YouTube.')) }
      document.head.appendChild(script)
    })
  }
  return loading
}

export function youtubeErrorMessage(code: number): string {
  if (code === 101 || code === 150) return 'O dono do vídeo bloqueou a reprodução fora do YouTube.'
  if (code === 100) return 'O vídeo foi removido ou ficou privado.'
  if (code === 5) return 'O navegador não conseguiu reproduzir este vídeo.'
  return 'O YouTube recusou este vídeo.'
}
