export type Screen = 'preferencias' | 'perfil' | 'sala' | 'roteiro' | 'player'

export const SCREEN_LABELS: Record<Screen, string> = {
  preferencias: 'Preferências',
  perfil: 'Perfil',
  sala: 'Sala',
  roteiro: 'Roteiro',
  player: 'Player',
}

/** Barra de etapas da sala. Etapas já liberadas são clicáveis. */
export function Steps({ screens, current, available, onSelect }: {
  screens: Screen[]
  current: Screen
  available: (screen: Screen) => boolean
  onSelect: (screen: Screen) => void
}) {
  const currentIndex = screens.indexOf(current)
  return (
    <nav aria-label="Etapas da noite" className="mb-6">
      <ol className="flex gap-1.5">
        {screens.map((screen, i) => {
          const enabled = available(screen) && screen !== current
          return (
            <li key={screen} className="flex-1">
              <button
                type="button"
                disabled={!enabled}
                onClick={() => onSelect(screen)}
                aria-current={screen === current ? 'step' : undefined}
                className="group w-full text-left disabled:cursor-default"
              >
                <div className={`h-1.5 rounded-full transition ${i <= currentIndex ? 'bg-hot' : 'bg-muted'} ${enabled ? 'group-hover:opacity-80' : ''}`} />
                <span className={`mt-1 block text-[11px] ${
                  screen === current ? 'font-semibold text-foreground'
                    : enabled ? 'text-muted-foreground group-hover:text-foreground' : 'text-muted-foreground/60'
                }`}>
                  {SCREEN_LABELS[screen]}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
