import { useEffect, useState } from 'react'

import { Button, Card, Kbd } from '../components/ui'
import { fetchResult, fetchStudy, isSnapshotMode, sendJudgment } from '../lib/api'
import { shuffle } from '../lib/shuffle'
import type { ProductResponse, StudyInfo, VariantId } from '../types'

/** Phase 1 of the note, one photo at a time: for each version (random order)
 *  realism (yes/no) then quality (1-5); then "best" among all the versions.
 *  Nothing is ever revealed: the tester judges photos, the tally does the accounting. */
type Step = { kind: 'realism'; i: number } | { kind: 'quality'; i: number } | { kind: 'best' }

type State =
  | { kind: 'loading' }
  | { kind: 'intro'; info: StudyInfo; tester: string; resume: number | null }
  | { kind: 'photo'; info: StudyInfo; tester: string; index: number; result: ProductResponse | null; versions: VariantId[]; step: Step; answered: number }
  | { kind: 'done'; info: StudyInfo; tester: string; answered: number }
  | { kind: 'error'; message: string }

const QUALITY = ['pessima', 'scarsa', 'sufficiente', 'buona', 'ottima']
const STEPS_PER_PHOTO = 7 // 3 versions x (realism + quality) + best

const progressKey = (tester: string) => `photo-lab:study:${tester}`
const readProgress = (tester: string): number | null => {
  try {
    const v = localStorage.getItem(progressKey(tester))
    return v === null ? null : Number(v)
  } catch {
    return null
  }
}
const writeProgress = (tester: string, index: number | null) => {
  try {
    if (index === null) localStorage.removeItem(progressKey(tester))
    else localStorage.setItem(progressKey(tester), String(index))
  } catch {
    /* no resume */
  }
}

export function StudioView() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    // ?tester=XX skips the intro (used for screenshots and for handing a tester a direct link)
    const preset = new URLSearchParams(window.location.search).get('tester')?.trim().slice(0, 12) ?? ''
    fetchStudy()
      .then((info) => (preset ? void load(info, preset, readProgress(preset) ?? 0, 0) : setState({ kind: 'intro', info, tester: '', resume: null })))
      .catch((err) => setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const load = async (info: StudyInfo, tester: string, index: number, answered: number) => {
    if (index >= info.ready.length) {
      writeProgress(tester, null)
      setState({ kind: 'done', info, tester, answered })
      return
    }
    writeProgress(tester, index)
    setState({ kind: 'photo', info, tester, index, result: null, versions: [], step: { kind: 'realism', i: 0 }, answered })
    try {
      const result = await fetchResult(info.ready[index])
      const versions = result ? shuffle(result.cards.filter((c) => c.changed && c.output).map((c) => c.variant)) : []
      if (!result || versions.length === 0) {
        void load(info, tester, index + 1, answered) // nothing to judge on this photo
        return
      }
      // ?q=quality|best jumps to that question on the first photo (screenshots)
      const jump = index === 0 ? new URLSearchParams(window.location.search).get('q') : null
      const step: Step = jump === 'quality' ? { kind: 'quality', i: 0 } : jump === 'best' ? { kind: 'best' } : { kind: 'realism', i: 0 }
      setState((s) => (s.kind === 'photo' && s.index === index ? { ...s, result, versions, step } : s))
    } catch (err) {
      setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }

  const answer = (value: string) => {
    if (state.kind !== 'photo' || !state.result) return
    const { result, versions, step, tester } = state
    const answered = state.answered + 1
    let next: Step | null
    if (step.kind === 'realism') {
      void sendJudgment({ image_id: result.image_id, task: 'realism', variant: versions[step.i], answer: value as 'yes' | 'no', shown: [versions[step.i]], order: versions, tester })
      next = { kind: 'quality', i: step.i }
    } else if (step.kind === 'quality') {
      void sendJudgment({ image_id: result.image_id, task: 'quality', variant: versions[step.i], answer: value as '1', shown: [versions[step.i]], order: versions, tester })
      next = step.i + 1 < versions.length ? { kind: 'realism', i: step.i + 1 } : { kind: 'best' }
    } else {
      void sendJudgment({ image_id: result.image_id, task: 'best', variant: value as VariantId | '', answer: '', shown: versions, order: versions, tester })
      next = null
    }
    if (next) setState({ ...state, step: next, answered })
    else void load(state.info, tester, state.index + 1, answered)
  }

  useEffect(() => {
    if (state.kind !== 'photo' || !state.result) return
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat) return
      const k = e.key.toLowerCase()
      const { step, versions } = state
      if (step.kind === 'realism' && (k === 'n' || k === 's')) answer(k === 's' ? 'yes' : 'no')
      if (step.kind === 'quality' && /^[1-5]$/.test(k)) answer(k)
      if (step.kind === 'best') {
        if (/^[1-3]$/.test(k) && versions[Number(k) - 1]) answer(versions[Number(k) - 1])
        if (k === '0') answer('')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])

  if (state.kind === 'loading') return <div className="skeleton h-64 rounded-lg" />
  if (state.kind === 'error') return <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-900">{state.message}</Card>

  if (state.kind === 'intro') {
    const { info } = state
    const testers = Object.keys(info.testers).length
    return (
      <div className="mx-auto max-w-2xl space-y-6 pt-6">
        <div className="text-center">
          <div className="mb-2 text-xs font-semibold text-brand-500">Studio · test cieco</div>
          <h2 className="text-[32px] leading-tight font-bold tracking-tight">{info.ready.length} foto di annunci veri, tre versioni ciascuna.</h2>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-neutral-600">
            Per ogni foto rispondi a tre domande: se una versione ti sembra alterata rispetto all’originale, che voto
            dai alla sua qualità, e quale delle tre useresti nell’annuncio. Non sai mai quale metodo ha prodotto cosa.
            Circa {info.ready.length * STEPS_PER_PHOTO} risposte, dieci minuti; puoi fermarti e riprendere dallo stesso punto.
          </p>
        </div>
        <Card className="space-y-4 p-5">
          <label className="block text-sm">
            <span className="font-medium">Le tue iniziali</span>
            <span className="text-muted"> · servono a distinguere i valutatori e a riprendere da dove eri</span>
            <input
              value={state.tester}
              onChange={(e) => {
                const tester = e.target.value.trim().slice(0, 12)
                setState({ ...state, tester, resume: tester ? readProgress(tester) : null })
              }}
              className="mt-2 w-full rounded-md border border-line bg-surface px-3 py-2.5 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
              placeholder="es. PS"
            />
          </label>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted">
              {isSnapshotMode() && 'Copia statica dei risultati: le risposte di questa sessione non vengono registrate · '}
              {info.ready.length < info.ids.length && `${info.ids.length - info.ready.length} foto ancora in elaborazione · `}
              {testers ? `${testers} valutatori finora` : 'nessun valutatore finora'}
            </span>
            <div className="flex gap-2">
              {state.resume !== null && state.resume > 0 && (
                <Button variant="outline" onClick={() => void load(info, state.tester, state.resume ?? 0, 0)}>
                  Riprendi dalla foto {(state.resume ?? 0) + 1}
                </Button>
              )}
              <Button disabled={!state.tester || info.ready.length === 0} onClick={() => void load(info, state.tester, 0, 0)}>
                {state.resume ? 'Ricomincia' : 'Inizia'}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    )
  }

  if (state.kind === 'done') {
    return (
      <div className="mx-auto max-w-2xl space-y-5 pt-10 text-center">
        <div className="text-xs font-semibold text-brand-500">Fine dello studio</div>
        <h2 className="text-[32px] leading-tight font-bold tracking-tight">Grazie, {state.tester}.</h2>
        <p className="text-[15px] text-neutral-600">
          {state.answered} risposte registrate. Il risultato di tutti i valutatori è nella vista Esperimento.
        </p>
        <div className="flex justify-center gap-3">
          <Button variant="ghost" onClick={() => setState({ kind: 'intro', info: state.info, tester: '', resume: null })}>
            Un altro valutatore
          </Button>
          <Button onClick={() => (window.location.search = '?view=esperimento')}>Vedi i risultati</Button>
        </div>
      </div>
    )
  }

  // ---- one photo, one question at a time
  const { info, index, result, versions, step } = state
  const card = (v: VariantId) => result?.cards.find((c) => c.variant === v)
  const stepNo = step.kind === 'best' ? STEPS_PER_PHOTO : step.i * 2 + (step.kind === 'quality' ? 2 : 1)
  const question =
    step.kind === 'realism'
      ? 'Vedi elementi finti, generati o strutturalmente diversi rispetto all’originale?'
      : step.kind === 'quality'
        ? 'Come giudichi luce, nitidezza e colori di questa foto?'
        : 'Se fossi l’agente, quale useresti nell’annuncio?'
  const frame = 'overflow-hidden rounded-lg border border-line bg-neutral-100'
  const tag = 'absolute top-2 left-2 z-10 rounded bg-black/60 px-2 py-0.5 text-[11px] font-semibold text-white'

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center justify-between text-xs text-muted">
          <span>
            Foto {index + 1} di {info.ready.length} · domanda {stepNo} di {STEPS_PER_PHOTO} · valutatore {state.tester}
          </span>
          <span>{step.kind === 'realism' ? 'Realismo' : step.kind === 'quality' ? 'Qualità' : 'Foto migliore'}</span>
        </div>
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-neutral-200">
          <div className="h-full bg-brand-500 transition-all" style={{ width: `${((index * STEPS_PER_PHOTO + stepNo - 1) / (info.ready.length * STEPS_PER_PHOTO)) * 100}%` }} />
        </div>
      </div>
      <h2 className="text-center text-[22px] leading-tight font-semibold tracking-tight">{question}</h2>

      {!result ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2].map((i) => (
            <div key={i} className="skeleton aspect-[4/3] rounded-lg" />
          ))}
        </div>
      ) : step.kind === 'realism' ? (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <div className={`relative ${frame}`}>
              <div className={tag}>Originale</div>
              <img src={result.original ?? ''} alt="Originale" className="max-h-[58vh] w-full object-contain" draggable={false} />
            </div>
            <div className={`relative ${frame}`}>
              <div className={tag}>Versione elaborata</div>
              <img src={card(versions[step.i])?.output ?? ''} alt="Elaborata" className="max-h-[58vh] w-full object-contain" draggable={false} />
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button size="lg" variant="outline" className="min-w-56" onClick={() => answer('no')}>
              No, è la stessa stanza <Kbd>N</Kbd>
            </Button>
            <Button size="lg" className="min-w-56" onClick={() => answer('yes')}>
              Sì, qualcosa è cambiato <Kbd>S</Kbd>
            </Button>
          </div>
        </>
      ) : step.kind === 'quality' ? (
        <>
          <div className={`mx-auto w-fit ${frame}`}>
            <img src={card(versions[step.i])?.output ?? ''} alt="Versione elaborata" className="max-h-[62vh] w-auto object-contain" draggable={false} />
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2">
            {QUALITY.map((label, i) => (
              <Button key={label} size="lg" variant="outline" className="min-w-32" onClick={() => answer(String(i + 1))}>
                {i + 1} · {label}
              </Button>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className={`relative mx-auto w-fit ${frame}`}>
            <div className={tag}>Originale</div>
            <img src={result.original ?? ''} alt="Originale" className="max-h-[26vh] w-auto object-contain" draggable={false} />
          </div>
          <div className={`grid gap-4 ${versions.length === 3 ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
            {versions.map((v, i) => (
              <div key={v} className="space-y-2">
                <div className={`relative ${frame}`}>
                  <div className={tag}>Versione {i + 1}</div>
                  <img src={card(v)?.output ?? ''} alt={`Versione ${i + 1}`} className="max-h-[40vh] w-full object-contain" draggable={false} />
                </div>
                <Button className="w-full" onClick={() => answer(v)}>
                  Userei la versione {i + 1} <Kbd>{i + 1}</Kbd>
                </Button>
              </div>
            ))}
          </div>
          <div className="flex justify-center">
            <Button variant="ghost" onClick={() => answer('')}>
              Nessuna, terrei l’originale <Kbd>0</Kbd>
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
