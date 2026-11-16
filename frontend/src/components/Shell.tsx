import type { ReactNode } from 'react'
import { LogOut, Mic2 } from 'lucide-react'

/** Moldura das telas: cabeçalho com marca (link para o início), código da sala e saída; rodapé. */
export function Shell({ children, code, onExit, onHome }: {
  children: ReactNode
  code?: string
  onExit?: () => void
  /** Mostra a tela inicial sem recarregar a página (e sem apagar o acesso à sala). */
  onHome?: () => void
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-[1210px] items-center gap-3 px-4 py-6 sm:px-7">
        <a
          href="/"
          aria-label="SingMatch — página inicial"
          onClick={event => {
            // Clique simples fica no app; Ctrl/Cmd/botão do meio abrem o link normalmente.
            if (!onHome || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
            event.preventDefault()
            onHome()
          }}
          className="flex items-center gap-2 rounded-full font-display text-xl font-extrabold text-foreground no-underline transition hover:opacity-85"
        >
          <span className="grid h-9 w-9 place-items-center rounded-full bg-hot text-primary-foreground" aria-hidden="true">
            <Mic2 className="h-5 w-5" />
          </span>
          <span>Sing<span className="text-hot">Match</span></span>
        </a>
        <span className="ml-auto flex items-center gap-2">
          {code && <span className="sm-chip border border-border font-mono tracking-widest text-accent">SALA {code}</span>}
          {onExit && (
            <button type="button" onClick={onExit} className="sm-btn border border-border bg-transparent px-3 py-1.5 text-xs text-muted-foreground hover:border-primary hover:text-foreground">
              <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">Sair deste dispositivo</span>
              <span className="sm:hidden">Sair</span>
            </button>
          )}
        </span>
      </header>

      <div className="flex-1">{children}</div>

      <footer className="mx-auto flex w-full max-w-[1210px] flex-col justify-between gap-1 border-t border-border px-4 py-5 text-[0.63rem] font-bold tracking-widest text-muted-foreground sm:flex-row sm:px-7">
        <span>SINGMATCH · PROJETO FERRAMENTA</span>
        <span>Forró · Piloto colaborativo · 2026</span>
      </footer>
    </div>
  )
}
