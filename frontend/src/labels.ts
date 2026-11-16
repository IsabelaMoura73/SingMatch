/** Mesma normalização de backend/app/matching.py (norm): sem acentos, minúsculas. */
export function norm(value: string) {
  return value.toLowerCase().trim().normalize('NFKD').replace(/\p{M}/gu, '')
    .replace(/[_-]/g, ' ').split(/\s+/).filter(Boolean).join(' ')
}

/**
 * Nome de exibição das características (clima e energia). O catálogo e a IA usam a
 * forma interna ("romantica", "energia media"); a tela mostra em português ("Romântica").
 */
const CHARACTERISTIC_LABELS: Record<string, string> = {
  animada: 'Animada',
  festiva: 'Festiva',
  romantica: 'Romântica',
  saudosa: 'Saudosa',
  sofrida: 'Sofrida',
  tranquila: 'Tranquila',
  'energia baixa': 'Energia baixa',
  'energia media': 'Energia média',
  'energia alta': 'Energia alta',
}

export function characteristicLabel(value: string) {
  const known = CHARACTERISTIC_LABELS[norm(value)]
  if (known) return known
  const text = value.trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Nome de exibição dos gêneros (o catálogo guarda "forro"). */
const GENRE_LABELS: Record<string, string> = { forro: 'Forró' }

export function genreLabel(value: string) {
  return GENRE_LABELS[norm(value)] ?? characteristicLabel(value)
}
