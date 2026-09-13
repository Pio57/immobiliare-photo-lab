import { useEffect, useState } from 'react'

import { Button, Card, SectionTitle } from '../components/ui'
import { fetchResult, fetchStudy, isSnapshotMode, sendChoice } from '../lib/api'
import type { ProductResponse, StudyInfo, VariantId, VersionCard } from '../types'

type Pair = { left: VariantId; right: VariantId }

type State =
  | { kind: 'loading' }
  | { kind: 'intro'; info: StudyInfo; tester: string }
  | { kind: 'photo'; info: StudyInfo; tester: string; index: number; result: ProductResponse | null; pairs: Pair[]; pairIndex: number; done: number }
  | { kind: 'done'; info: StudyInfo; tester: string; count: number }
  | { kind: 'error'; message: string }

/** Every pair of the versions that exist for this photo, each with a random side. */
function makePairs(cards: VersionCard[]): Pair[] {
  const ids = cards.filter((c) => c.changed && c.output).map((c) => c.variant)
  const pairs: Pair[] = []
  for (let i = 0; i < ids.length; i++)
    for (let k = i + 1; k < ids.length; k++) {
      const [a, b] = Math.random() < 0.5 ? [ids[i], ids[k]] : [ids[k], ids[i]]
      pairs.push({ left: a, right: b })
    }
  return pairs.sort(() => Math.random() - 0.5)
}

/** The blind study, pairwise: the original on top, two versions below, left or
 *  right (or tie) with the arrow keys. Nothing is revealed, ever: the tester
 *  judges photos, the tally (Esperimento view) does the accounting. */
export function StudioView() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    fetchStudy()
      .then((info) => setState({ kind: 'intro', info, tester: '' }))
      .catch((err) => setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) }))
  }, [])

  const load = async (info: StudyInfo, tester: string, index: number, done: number) => {
    if (index >= info.ready.length) {
      setState({ kind: 'done', info, tester, count: done })
      return
    }
    setState({ kind: 'photo', info, tester, index, result: null, pairs: [], pairIndex: 0, done })
    try {
      const result = await fetchResult(info.ready[index])
      const pairs = result ? makePairs(result.cards) : []
      if (!result || pairs.length === 0) {
        void load(info, tester, index + 1, done) // nothing to compare on this photo
        return
      }
      setState((s) => (s.kind === 'photo' && s.index === index ? { ...s, result, pairs } : s))
    } catch (err) {
      setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }

  const judge = async (winner: 'left' | 'right' | 'tie') => {
    if (state.kind !== 'photo' || !state.result || state.pairIndex >= state.pairs.length) return
    const r = state.result
    const pair = state.pairs[state.pairIndex]
    const chosen = winner === 'tie' ? 'tie' : pair[winner]
    const done = state.done + 1
    if (state.pairIndex + 1 >= state.pairs.length) void load(state.info, state.tester, state.index + 1, done)
    else setState({ ...state, pairIndex: state.pairIndex + 1, done })
    try {
      await sendChoice({ image_id: r.image_id, chosen, shown: [pair.left, pair.right], order: [pair.left, pair.right], tester: state.tester })
    } catch {
      /* the tally misses this one; the study goes on */
    }
  }

  useEffect(() => {
    if (state.kind !== 'photo') return
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat) return
      if (e.key === 'ArrowLeft') void judge('left')
      if (e.key === 'ArrowRight') void judge('right')
      if (e.key === 'ArrowDown') void judge('tie')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])

  if (state.kind === 'loading') return <div className="skeleton h-64 rounded-2xl" />
  if (state.kind === 'error') return <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-900">{state.message}</Card>

  if (state.kind === 'intro') {
    const { info } = state
    const testers = Object.keys(info.testers).length
    return (
      <div className="mx-auto max-w-2xl space-y-6 pt-4">
        <div className="text-center">
          <div className="mb-3 text-[11px] font-semibold tracking-[0.14em] text-brand-500 uppercase">Studio cieco</div>
          <h2 className="font-display text-4xl leading-tight font-medium">
            {info.ready.length} foto, tre versioni ciascuna, a coppie.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-neutral-600">
            In alto l&apos;originale, sotto due versioni corrette. Quale useresti come copertina? Freccia sinistra o
            destra; freccia giù se non le distingui. Tre coppie per foto, {info.ready.length * 3} confronti in tutto,
            ~10 s l&apos;uno. Nessun nome, nessun dettaglio: solo le foto. Il conto lo fa il tabellone.
          </p>
        </div>
        <Card className="space-y-4 p-5">
          <label className="block text-sm">
            <span className="text-muted">Le tue iniziali (per distinguere i tester)</span>
            <input
              value={state.tester}
              onChange={(e) => setState({ ...state, tester: e.target.value.trim().slice(0, 12) })}
              className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500/40 focus:outline-none"
              placeholder="es. PS"
            />
          </label>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted">
              {isSnapshotMode() && 'Copia statica dei risultati: i giudizi di questa sessione non vengono registrati · '}
              {info.ready.length < info.ids.length && `${info.ids.length - info.ready.length} foto ancora in elaborazione · `}
              {testers ? `${testers} tester finora` : 'nessun tester finora'}
            </span>
            <Button disabled={!state.tester || info.ready.length === 0} onClick={() => void load(info, state.tester, 0, 0)}>
              Inizia
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  if (state.kind === 'done') {
    return (
      <div className="mx-auto max-w-2xl space-y-6 pt-4 text-center">
        <div className="text-[11px] font-semibold tracking-[0.14em] text-brand-500 uppercase">Fine dello studio</div>
        <h2 className="font-display text-4xl leading-tight font-medium">Grazie, {state.tester}.</h2>
        <p className="text-[15px] text-neutral-600">
          {state.count} confronti registrati. Il risultato di tutti i tester è nella vista Esperimento.
        </p>
        <div className="flex justify-center gap-3">
          <Button variant="ghost" onClick={() => setState({ kind: 'intro', info: state.info, tester: '' })}>
            Un altro tester
          </Button>
          <Button onClick={() => (window.location.search = '?view=esperimento')}>Vedi il tabellone</Button>
        </div>
      </div>
    )
  }

  // ---- one photo, one pair at a time
  const { info, index, result, pairs, pairIndex } = state
  const pair = result ? pairs[pairIndex] : null
  const card = (v: VariantId) => result?.cards.find((c) => c.variant === v)

  return (
    <div className="space-y-4">
      <SectionTitle
        eyebrow={`Foto ${index + 1} di ${info.ready.length} · coppia ${Math.min(pairIndex + 1, pairs.length || 1)} di ${pairs.length || 3} · tester ${state.tester}`}
        title="Quale useresti come copertina?"
        hint="← sinistra · → destra · ↓ non le distinguo"
      />
      {!result || !pair ? (
        <div className="space-y-4">
          <div className="skeleton mx-auto aspect-[4/3] w-full max-w-md rounded-2xl" />
          <div className="grid gap-4 md:grid-cols-2">
            {[1, 2].map((i) => (
              <div key={i} className="skeleton aspect-[4/3] rounded-2xl" />
            ))}
          </div>
        </div>
      ) : (
        <>
          <Card className="relative mx-auto w-fit overflow-hidden">
            <div className="absolute top-2 left-2 z-10 rounded-md bg-black/60 px-2 py-1 text-[11px] font-semibold text-white backdrop-blur">
              Originale
            </div>
            <img src={result.original ?? ''} alt="Originale" className="max-h-[34vh] w-auto object-contain" draggable={false} />
          </Card>
          <div className="grid gap-4 md:grid-cols-2">
            {(['left', 'right'] as const).map((side) => (
              <Card key={side} className="relative overflow-hidden">
                <div className="absolute top-2 left-2 z-10 rounded-md bg-black/60 px-2 py-1 text-[11px] font-semibold text-white backdrop-blur">
                  {side === 'left' ? 'Sinistra ←' : 'Destra →'}
                </div>
                <img src={card(pair[side])?.output ?? ''} alt={side} className="max-h-[52vh] w-full object-contain" draggable={false} />
              </Card>
            ))}
          </div>
          <div className="flex items-center justify-center gap-3">
            <Button className="min-w-36" onClick={() => void judge('left')}>
              ← Sinistra
            </Button>
            <Button variant="ghost" onClick={() => void judge('tie')}>
              ↓ Non le distinguo
            </Button>
            <Button className="min-w-36" onClick={() => void judge('right')}>
              Destra →
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
