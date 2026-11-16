import { useState, type FormEvent } from 'react'
import { Sparkles, Users } from 'lucide-react'

const CODE_LENGTH = 8

/** Limpa o código digitado: só letras e números, em maiúsculas. */
export function cleanCode(value: string) {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, CODE_LENGTH)
}

/** Tela inicial: criar sala (organizador, cantando ou não) ou entrar com código. */
export function Home({ busy, creating, joining, initialCode, onCreate, onJoin }: {
  busy: boolean
  creating: boolean
  joining: boolean
  initialCode: string
  /** `hostName` é null quando o organizador não vai cantar. */
  onCreate: (intention: string, hostName: string | null) => void
  onJoin: (code: string, name: string) => void
}) {
  const [intention, setIntention] = useState('Começar tranquilo e terminar animado')
  const [willSing, setWillSing] = useState(true)
  const [hostName, setHostName] = useState('')
  const [code, setCode] = useState(cleanCode(initialCode))
  const [name, setName] = useState('')

  const canCreate = !willSing || hostName.trim().length > 0
  const canJoin = code.length === CODE_LENGTH && name.trim().length > 0

  const submitCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (canCreate) onCreate(intention.trim(), willSing ? hostName.trim() : null)
  }
  const submitJoin = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (canJoin) onJoin(code, name.trim())
  }

  return (
    <div className="mx-auto max-w-3xl px-1 pb-8">
      <section className="py-8 text-center">
        <div className="mb-5 flex h-10 items-end justify-center gap-1" aria-hidden="true">
          {[0, 1, 2, 3, 4, 5, 6].map(i => (
            <span key={i} className="eq-bar w-2 rounded-full bg-hot" style={{ height: 40, animationDelay: `${i * 0.12}s` }} />
          ))}
        </div>
        <h1 className="mb-0 text-5xl leading-[1.05] font-extrabold sm:text-6xl">
          Ninguém briga<br /><span className="text-hot">pelo microfone.</span>
        </h1>
        <p className="mx-auto mt-4 mb-0 max-w-md text-muted-foreground">
          Cada amigo conta o que curte, a IA monta o roteiro da noite
        </p>
      </section>

      <div className="grid gap-5 md:grid-cols-2">
        <form className="sm-card flex min-h-[30rem] flex-col gap-4 sm:p-7" onSubmit={submitCreate} aria-labelledby="criar-sala">
          <h2 id="criar-sala" className="flex items-center gap-2 text-xl font-bold">
            <Sparkles className="h-5 w-5 text-accent" aria-hidden="true" />Criar sala
          </h2>
          <p className="text-sm text-muted-foreground">Para quem organiza: crie a sala e compartilhe o código com o grupo.</p>
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            Gênero <span className="sm-chip border border-border text-foreground">Forró · piloto</span>
          </p>
          <textarea
            className="sm-input min-h-24"
            aria-label="Intenção da noite"
            placeholder="Intenção da noite — ex.: aniversário, começar leve e terminar pulando"
            maxLength={500}
            value={intention}
            onChange={e => setIntention(e.target.value)}
          />
          <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-border bg-background/40 px-4 py-3">
            <input
              type="checkbox"
              className="h-4 w-4 shrink-0 accent-primary"
              checked={willSing}
              onChange={e => setWillSing(e.target.checked)}
            />
            <span className="text-sm font-semibold">Também vou cantar</span>
          </label>
          {willSing && (
            <input
              className="sm-input"
              aria-label="Seu nome"
              placeholder="Seu nome"
              maxLength={80}
              required
              value={hostName}
              onChange={e => setHostName(e.target.value)}
            />
          )}
          <button className="sm-btn-primary mt-auto w-full" disabled={busy || !canCreate}>
            {creating ? 'Criando sala...' : 'Criar e pegar código'}
          </button>
        </form>

        <form className="sm-card flex min-h-[30rem] flex-col gap-4 sm:p-7" onSubmit={submitJoin} aria-labelledby="entrar-sala">
          <h2 id="entrar-sala" className="flex items-center gap-2 text-xl font-bold">
            <Users className="h-5 w-5 text-neon" aria-hidden="true" />Entrar com código
          </h2>
          <p className="text-sm text-muted-foreground">Recebeu um código? Entre com seu nome e se&nbsp;divirta!</p>
          <ol className="flex flex-col gap-2 text-sm text-muted-foreground">
            {['Conte seus gostos', 'Confirme o que a IA entendeu', 'Cante quando chegar sua vez'].map((step, i) => (
              <li key={step} className="flex items-center gap-2">
                <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-secondary text-[11px] font-bold text-foreground">{i + 1}</span>
                {step}
              </li>
            ))}
          </ol>
          <input
            className="sm-input"
            aria-label="Seu nome"
            placeholder="Seu nome"
            maxLength={80}
            required
            value={name}
            onChange={e => setName(e.target.value)}
          />
          <input
            className="sm-input text-center font-mono text-2xl tracking-[0.3em] uppercase"
            aria-label="Código da sala"
            placeholder="AB12CD34"
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            maxLength={CODE_LENGTH}
            required
            value={code}
            onChange={e => setCode(cleanCode(e.target.value))}
          />
          {/* Texto e botão no fim do card, alinhados com o botão de "Criar sala". */}
          <div className="mt-auto flex flex-col gap-4">
            <p className="text-xs text-muted-foreground">Sem cadastro. Só nome e código.</p>
            <button className="sm-btn-ghost w-full" disabled={busy || !canJoin}>
              {joining ? 'Entrando...' : 'Entrar na sala'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
