import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Ban, Check, ChevronDown, Heart, HelpCircle, Mic, Plus, Users, Wand2, X } from 'lucide-react'
import type { OwnProfile, PreferenceCategory, PreferenceLabel, Profile } from '../api'
import { characteristicLabel, genreLabel, norm } from '../labels'

export const CATEGORY_NAMES: Record<PreferenceCategory, string> = {
  genre: 'Gênero', artist: 'Artista', song: 'Música', tag: 'Característica',
}

/** Sugestões que o participante pode juntar ao texto com um clique. */
const EXAMPLES = ['Amo Luiz Gonzaga', 'Quero música animada', 'Nada de música romântica', 'Prefiro cantar solo']

/** Sugestões com o mesmo acabamento dos campos e cards do restante da interface. */
function CharacteristicPicker({ value, suggestions, label, onChange }: {
  value: string
  suggestions: string[]
  label: string
  onChange: (value: string) => void
}) {
  const listId = useId()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const options = suggestions
  useEffect(() => {
    if (open) listRef.current?.children[activeIndex]?.scrollIntoView({ block: 'nearest' })
  }, [open, activeIndex])
  const choose = (tag: string) => {
    onChange(tag)
    setOpen(false)
    setActiveIndex(-1)
    triggerRef.current?.focus()
  }

  return (
    <div className="relative min-w-0 flex-1" onBlur={event => {
      if (!event.currentTarget.contains(event.relatedTarget)) { setOpen(false); setActiveIndex(-1) }
    }}>
      <div className="relative">
        <button
          ref={triggerRef}
          type="button"
          className="sm-input cursor-pointer py-2.5 pr-11 text-left text-sm"
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          aria-controls={listId}
          aria-activedescendant={open && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
          onClick={() => { setOpen(!open); setActiveIndex(-1) }}
          onKeyDown={event => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
              event.preventDefault()
              setOpen(true)
              if (!options.length) return
              const next = event.key === 'ArrowDown'
                ? (activeIndex + 1) % options.length
                : (activeIndex < 0 ? options.length : activeIndex) - 1
              setActiveIndex((next + options.length) % options.length)
            } else if (event.key === 'Escape') {
              event.preventDefault(); setOpen(false); setActiveIndex(-1)
            } else if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              if (open && options[activeIndex]) choose(options[activeIndex])
              else setOpen(!open)
            }
          }}
        >
          <span className={`block truncate ${value ? '' : 'text-muted-foreground'}`}>
            {value ? characteristicLabel(value) : 'Escolha uma característica…'}
          </span>
          <ChevronDown className={`absolute top-1/2 right-4 h-4 w-4 -translate-y-1/2 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
        </button>
      </div>
      {open && (
        <div className="absolute inset-x-0 top-full z-20 mt-2 rounded-2xl border border-border bg-card p-2 shadow-xl shadow-black/30">
          <ul ref={listRef} id={listId} role="listbox" aria-label="Características disponíveis" className="m-0 max-h-60 space-y-1 overflow-y-auto overscroll-contain p-0 pr-1">
            {options.map((tag, index) => {
              const selected = norm(value) === norm(tag)
              return (
                <li key={tag} id={`${listId}-${index}`} role="option" aria-selected={selected}
                  className={`flex cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${index === activeIndex || selected ? 'bg-primary/15 text-primary' : 'text-foreground hover:bg-secondary'}`}
                  onMouseDown={event => event.preventDefault()}
                  onClick={() => choose(tag)}>
                  <span>{characteristicLabel(tag)}</span>
                  {selected && <Check className="h-4 w-4 shrink-0" aria-hidden="true" />}
                </li>
              )
            })}
          </ul>
          {options.length === 0 && <p className="m-0 px-3 py-2 text-sm text-muted-foreground">Nenhuma sugestão encontrada.</p>}
        </div>
      )}
    </div>
  )
}

/** Lista editável de gostos ou vetos: cada item mostra categoria e a evidência no texto. */
function LabelList({ labels, tone, addLabel, tagSuggestions, onChange }: {
  labels: PreferenceLabel[]
  tone: 'like' | 'veto'
  addLabel: string
  /** Características que o matching entende (climas do catálogo e faixas de energia). */
  tagSuggestions: string[]
  onChange: (labels: PreferenceLabel[]) => void
}) {
  const [category, setCategory] = useState<PreferenceCategory>('tag')
  const [value, setValue] = useState('')
  const toneClass = tone === 'like' ? 'text-primary' : 'text-destructive'
  // Veto de característica só funciona com termos que o matching conhece; outros bloqueiam todas as músicas.
  const known = new Set(tagSuggestions.map(norm))
  const closedTags = tone === 'veto' && category === 'tag'
  const unknownVeto = (label: PreferenceLabel) => tone === 'veto' && label.category === 'tag' && known.size > 0 && !known.has(norm(label.value))
  const add = () => {
    const cleaned = value.trim()
    if (!cleaned || cleaned.length > 150) return
    if (category === 'tag' && !known.has(norm(cleaned))) return
    if (labels.some(item => item.category === category && norm(item.value) === norm(cleaned))) return
    onChange([...labels, { category, value: cleaned, evidence: 'Correção informada diretamente pelo participante.', origin: 'correcao_usuario' }])
    setValue('')
  }
  // Características e gêneros aparecem em português; o valor guardado continua o interno.
  const shown = (label: PreferenceLabel) =>
    label.category === 'tag' ? characteristicLabel(label.value) : label.category === 'genre' ? genreLabel(label.value) : label.value
  return (
    <div className="flex flex-col gap-3">
      {labels.length === 0
        ? <p className="mb-0 rounded-xl border border-dashed border-border bg-background/30 px-4 py-3 text-sm text-muted-foreground">Nada por aqui.</p>
        : <ul className="m-0 flex flex-col gap-2 p-0">
            {labels.map((label, index) => (
              <li key={`${label.category}-${label.value}-${index}`} className="flex min-w-0 list-none items-start gap-3 rounded-2xl border border-border bg-background/40 p-4">
                <span className="flex min-w-0 flex-1 flex-col gap-1">
                  <span className={`text-[10px] font-semibold tracking-wider uppercase ${toneClass}`}>{CATEGORY_NAMES[label.category]}</span>
                  <span className="text-sm font-semibold break-words">{shown(label)}</span>
                  <span className="text-xs text-muted-foreground break-words">
                    {label.origin === 'texto' ? `“${label.evidence}”` : 'Adicionado por você'}
                  </span>
                  {unknownVeto(label) && (
                    <span className="mt-1 text-xs font-semibold text-destructive" role="status">
                      Característica desconhecida: remova e escolha uma da lista.
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border-0 bg-secondary p-0 text-muted-foreground transition hover:text-destructive"
                  onClick={() => onChange(labels.filter((_, i) => i !== index))}
                  aria-label={`Remover ${shown(label)}`}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>}
      <div className="flex flex-col gap-2 border-t border-border pt-4">
        <div className="relative">
          <select
            className="sm-input appearance-none py-2.5 pr-11 text-sm"
            aria-label={`Categoria para ${addLabel}`}
            value={category}
            onChange={e => { setCategory(e.target.value as PreferenceCategory); setValue('') }}
          >
            {Object.entries(CATEGORY_NAMES).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute top-1/2 right-4 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          {category === 'tag' ? (
            <CharacteristicPicker value={value} suggestions={tagSuggestions} label={addLabel} onChange={setValue} />
          ) : (
            <input
              className="sm-input min-w-0 flex-1 py-2.5 text-sm"
              aria-label={addLabel}
              placeholder={`+ ${addLabel}`}
              maxLength={150}
              value={value}
              onChange={e => setValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
            />
          )}
          <button type="button" className="sm-btn-ghost shrink-0 px-4 py-2.5 text-sm" onClick={add} disabled={!value.trim()}>
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />Adicionar
          </button>
        </div>
      </div>
      {closedTags && (
        <p className="mb-0 text-xs text-muted-foreground">
          Para vetar uma característica, escolha uma das que o catálogo usa. Para vetar uma música ou artista, troque a categoria.
        </p>
      )}
    </div>
  )
}

/** Grupo de botões de escolha única (estilo "pílula"). */
function Choice<T extends string>({ label, value, options, onChange }: {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
      {options.map(option => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={`sm-btn ${value === option.value ? 'border border-neon bg-neon text-primary-foreground' : 'border border-border bg-secondary text-secondary-foreground hover:border-primary'}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

function SectionTitle({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return <h3 className="m-0 flex items-center gap-2 text-base font-bold">{icon}{children}</h3>
}

type ProfileScreenProps = {
  name: string
  intention: string
  own: OwnProfile | null
  rawText: string
  interpretedText: string
  draft: Profile | null
  busy: boolean
}

/** Tela "Preferências": o participante escreve do que gosta e a IA interpreta. */
export function PreferencesScreen({ name, intention, rawText, interpretedText, draft, busy, interpreting, onTextChange, onInterpret, onReview }: ProfileScreenProps & {
  interpreting: boolean
  onTextChange: (text: string) => void
  onInterpret: (event: FormEvent<HTMLFormElement>) => void
  /** Vai para a revisão sem reinterpretar (quando o texto não mudou). */
  onReview: () => void
}) {
  const textChanged = rawText.trim() !== interpretedText
  return (
    <section className="sm-card sm:p-8" aria-labelledby="perfil-titulo">
      <p className="mb-0 text-sm text-muted-foreground">
        Oi, {name}! {intention ? <>A noite é: <span className="text-foreground">“{intention}”</span></> : 'Conte o que você curte.'}
      </p>
      <h1 id="perfil-titulo" className="mt-3 mb-1 text-3xl font-bold">O que você curte cantar?</h1>
      <p className="mb-0 text-muted-foreground">
        Escreva do seu jeito: artistas, músicas, estilos — e o que você <strong className="text-primary">não</strong> quer cantar.
        A IA interpreta, mas quem confirma é você.
      </p>

      <form onSubmit={onInterpret}>
        <textarea
          className="sm-input mt-5 min-h-44 text-base"
          aria-label="Conte seus gostos musicais"
          rows={6}
          minLength={3}
          maxLength={2000}
          required
          value={rawText}
          onChange={e => onTextChange(e.target.value)}
          placeholder="Ex.: Gosto de forró animado e de Luiz Gonzaga. Não quero músicas românticas. Prefiro cantar sozinha."
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map(example => (
            <button
              key={example}
              type="button"
              onClick={() => onTextChange((rawText.trim() ? rawText.trim().replace(/[.!]?$/, '. ') : '') + example + '.')}
              className="sm-chip border border-border bg-secondary text-secondary-foreground hover:border-primary"
            >
              + {example}
            </button>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          {draft && !textChanged && (
            <button type="button" className="sm-btn-ghost" onClick={onReview} disabled={busy}>Ver o que a IA entendeu</button>
          )}
          <button className="sm-btn-primary flex-1" disabled={busy || rawText.trim().length < 3}>
            <Wand2 className={`h-4 w-4 ${interpreting ? 'animate-spin' : ''}`} aria-hidden="true" />
            {interpreting ? 'A IA está lendo seu gosto…' : draft ? 'Interpretar novamente' : 'Interpretar com IA'}
          </button>
        </div>
        <p className="mt-2 mb-0 text-center text-xs text-muted-foreground">Seu texto é enviado a um serviço de IA (OpenAI). Os outros participantes não veem o que você escreveu.</p>
      </form>
    </section>
  )
}

/** Tela "Perfil": revisar o que a IA entendeu, corrigir e confirmar. */
export function ReviewScreen({ name, own, rawText, interpretedText, draft, busy, tagSuggestions, confirming, onDraftChange, onConfirm, onRewrite }: ProfileScreenProps & {
  draft: Profile
  tagSuggestions: string[]
  confirming: boolean
  onDraftChange: (profile: Profile) => void
  onConfirm: () => void
  onRewrite: () => void
}) {
  const textChanged = rawText.trim() !== interpretedText
  const duetValue = draft.duet_allowed === null ? 'unknown' : String(draft.duet_allowed)
  return (
    <section className="flex flex-col gap-4" aria-labelledby="revisao-titulo">
      <div>
        <h1 id="revisao-titulo" className="mb-1 text-3xl font-bold">Entendi assim, {name} 🎤</h1>
        <p className="mb-0 text-muted-foreground">Remova o que a IA entendeu errado, acrescente o que faltou e confirme.</p>
        {interpretedText && (
          <blockquote className="mx-0 mt-4 mb-0 border-l-2 border-primary pl-4 text-sm text-muted-foreground italic">“{interpretedText}”</blockquote>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="sm-card relative flex flex-col gap-3 focus-within:z-10">
          <SectionTitle icon={<Heart className="h-4 w-4 text-primary" aria-hidden="true" />}>Gostos</SectionTitle>
          <LabelList labels={draft.likes} tone="like" addLabel="adicionar gosto" tagSuggestions={tagSuggestions} onChange={likes => onDraftChange({ ...draft, likes })} />
        </div>
        <div className="sm-card relative flex flex-col gap-3 focus-within:z-10">
          <SectionTitle icon={<Ban className="h-4 w-4 text-destructive" aria-hidden="true" />}>Vetos</SectionTitle>
          <p className="mb-0 text-xs text-muted-foreground">O roteiro nunca vai te dar uma música vetada.</p>
          <LabelList labels={draft.vetoes} tone="veto" addLabel="adicionar veto" tagSuggestions={tagSuggestions} onChange={vetoes => onDraftChange({ ...draft, vetoes })} />
        </div>
        <div className="sm-card flex flex-col gap-3">
          <SectionTitle icon={<Mic className="h-4 w-4 text-neon" aria-hidden="true" />}>Formato preferido</SectionTitle>
          <Choice
            label="Formato preferido"
            value={draft.preferred_format}
            options={[{ value: 'solo', label: 'Solo' }, { value: 'dueto', label: 'Dueto' }, { value: 'indiferente', label: 'Tanto faz' }]}
            onChange={preferred_format => onDraftChange({ ...draft, preferred_format })}
          />
        </div>
        <div className="sm-card flex flex-col gap-3">
          <SectionTitle icon={<Users className="h-4 w-4 text-neon" aria-hidden="true" />}>Topa dueto?</SectionTitle>
          <Choice
            label="Permite duetos"
            value={duetValue as 'true' | 'false' | 'unknown'}
            options={[{ value: 'true', label: 'Sim' }, { value: 'false', label: 'Não' }, { value: 'unknown', label: 'Não informei' }]}
            onChange={v => onDraftChange({ ...draft, duet_allowed: v === 'unknown' ? null : v === 'true' })}
          />
        </div>
      </div>

      {draft.questions.length > 0 && (
        <div className="sm-card flex flex-col gap-2 border-accent/40">
          <SectionTitle icon={<HelpCircle className="h-4 w-4 text-accent" aria-hidden="true" />}>Dúvidas da IA</SectionTitle>
          <ul className="m-0 space-y-1 pl-5 text-sm text-muted-foreground">
            {draft.questions.map((question, i) => <li key={i}>{question}</li>)}
          </ul>
          <p className="mb-0 text-xs text-muted-foreground">Se algo estiver ambíguo, reescreva e interprete de novo, ou corrija os itens acima.</p>
        </div>
      )}

      {textChanged && (
        <p className="m-0 rounded-xl border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-accent" role="status">
          Você alterou o texto. Volte em “Reescrever” e interprete de novo antes de confirmar.
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <button type="button" className="sm-btn-ghost" onClick={onRewrite} disabled={busy}>Reescrever</button>
        <button type="button" className="sm-btn-primary flex-1" disabled={busy || textChanged} onClick={onConfirm}>
          <Check className="h-4 w-4" aria-hidden="true" />
          {confirming ? 'Salvando...' : own?.confirmed ? 'Salvar correções do perfil' : 'Confirmar perfil'}
        </button>
      </div>
      {own?.confirmed && !textChanged && (
        <p className="m-0 text-center text-xs text-neon" role="status">✓ Perfil confirmado. Se mudar algo, confirme de novo.</p>
      )}
    </section>
  )
}
