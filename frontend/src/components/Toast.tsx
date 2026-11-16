import { CheckCircle2, TriangleAlert, X } from 'lucide-react'

/** Aviso flutuante no canto da tela (erro ou sucesso), com botão de fechar. */
export function Toast({ tone, title, message, onClose }: {
  tone: 'error' | 'success'
  title?: string
  message: string
  onClose: () => void
}) {
  const error = tone === 'error'
  return (
    <div
      role={error ? 'alert' : 'status'}
      className={`fixed right-4 bottom-4 z-20 flex w-[min(420px,calc(100vw-2rem))] items-start gap-3 rounded-2xl border bg-card/95 p-4 pr-12 text-sm shadow-2xl backdrop-blur sm:right-5 sm:bottom-5 ${
        error ? 'border-destructive/50 text-foreground' : 'border-neon/40 text-foreground'
      }`}
    >
      {error
        ? <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
        : <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-neon" aria-hidden="true" />}
      <div className="flex min-w-0 flex-col gap-0.5">
        {title && <strong className={error ? 'text-destructive' : 'text-neon'}>{title}</strong>}
        <span className="break-words text-muted-foreground">{message}</span>
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label={error ? 'Fechar erro' : 'Fechar aviso'}
        className="absolute top-3 right-3 grid h-7 w-7 place-items-center rounded-full text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  )
}
