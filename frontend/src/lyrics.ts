/** Leitura de LRC ([mm:ss.xx]texto) e cálculo da linha ativa. */
export type LyricLine = { time: number; text: string }

const LINE = /^\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\](.*)$/

export function parseLrc(lrc: string): LyricLine[] {
  const lines: LyricLine[] = []
  for (const raw of lrc.split(/\r?\n/)) {
    const match = LINE.exec(raw.trim())
    if (!match) continue
    const fraction = match[3] ? Number(`0.${match[3]}`) : 0
    lines.push({ time: Number(match[1]) * 60 + Number(match[2]) + fraction, text: match[4].trim() })
  }
  return lines.sort((a, b) => a.time - b.time)
}

/** Índice da última linha que já começou, ou -1 antes da primeira. */
export function activeLine(lines: LyricLine[], time: number): number {
  let lo = 0, hi = lines.length - 1, found = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (lines[mid].time <= time) { found = mid; lo = mid + 1 } else hi = mid - 1
  }
  return found
}

/** Progresso 0..1 dentro da linha ativa (para o efeito de preenchimento do karaokê). */
export function lineProgress(lines: LyricLine[], index: number, time: number): number {
  if (index < 0 || index >= lines.length) return 0
  const start = lines[index].time
  const end = index + 1 < lines.length ? lines[index + 1].time : start + 4
  const span = Math.max(0.5, Math.min(end - start, 10))
  return Math.min(1, Math.max(0, (time - start) / span))
}
