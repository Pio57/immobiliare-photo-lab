import { CompareSlider } from './CompareSlider'
import { Button, Card, secs, usd } from './ui'
import { DEFECT_LABEL, VARIANT_LABEL, VARIANT_SUBTITLE, type ModuleName, type Step, type VersionCard } from '../types'

const MODULES: ModuleName[] = ['Risoluzione', 'Colore', 'Luce', 'Pulizia', 'Raddrizza', 'Nitidezza']

export const label = (d: string) => DEFECT_LABEL[d] ?? d.replace(/_/g, ' ')

export function Chip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'warn' | 'ok' | 'brand' }) {
  const style = {
    neutral: 'bg-neutral-100 text-neutral-700 ring-neutral-500/15',
    warn: 'bg-amber-50 text-amber-800 ring-amber-600/25',
    ok: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    brand: 'bg-brand-50 text-brand-600 ring-brand-500/25',
  }[tone]
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${style}`}>
      {children}
    </span>
  )
}

/** One correction module: ran / skipped by the gate / not needed. */
function StepRow({ step }: { step: Step }) {
  const state = !step.needed ? 'idle' : step.applied ? 'applied' : 'rejected'
  const dot = { idle: 'bg-neutral-300', applied: 'bg-emerald-500', rejected: 'bg-amber-500' }[state]
  const params = step.params
    ? Object.entries(step.params)
        .filter(([k, v]) => v !== 0 && v !== 1 && k !== 'latency_ms' && k !== 'cost_usd' && v !== undefined)
        .map(([k, v]) =>
          k === 'plan_adjusted'
            ? `piano adattato: ${v}`
            : k === 'crop_pct'
              ? `ritaglio ${Math.round(Number(v))}%`
              : `${k} ${typeof v === 'number' ? +v.toFixed(2) : v}`,
        )
        .join(' · ')
    : ''
  return (
    <li className={`flex items-baseline gap-2 py-1 text-xs ${state === 'idle' ? 'opacity-45' : ''}`}>
      <span className={`h-2 w-2 shrink-0 translate-y-[-1px] rounded-full ${dot}`} />
      <span className="w-20 shrink-0 font-medium">{step.module}</span>
      <span className="min-w-0 flex-1 truncate text-neutral-700" title={params}>
        {state === 'idle'
          ? 'non necessario'
          : state === 'rejected'
            ? `fermato dal controllo di fedeltà${params ? ` (${params})` : ''}`
            : params || 'applicato'}
        {step.retried && state === 'applied' && ' · 2º tentativo'}
      </span>
      {step.fidelity && <span className="shrink-0 text-muted tabular-nums">{step.fidelity.score.toFixed(3)}</span>}
    </li>
  )
}

/** The stack: the three versions one below the other, each one large, each with its
 *  own before/after handle and its own "choose" button, so the tester sees all three
 *  at once and scrolls. Details (what was corrected, by whom, cost) appear only after
 *  the choice: in blind mode the photo is the only evidence. */
export function VersionStack({
  cards,
  original,
  revealed,
  chosen,
  onChoose,
  onKeep,
  blindGate,
  hideGate,
}: {
  cards: VersionCard[]
  original: string
  revealed: boolean
  chosen: string | null | undefined
  onChoose?: (variant: VersionCard['variant']) => void
  onKeep?: () => void
  /** study: hide the gate verdict until the choice and let a rejected version be chosen */
  blindGate?: boolean
  /** study reveal: never mention the gate here, it belongs to the tally */
  hideGate?: boolean
}) {
  const showGate = !hideGate && (revealed || !blindGate)
  const name = (c: VersionCard) => (revealed ? VARIANT_LABEL[c.variant] : `Versione ${c.blind_id.slice(1)}`)
  return (
    <div className="space-y-6">
      {cards.map((card) => {
        const d = card.diagnosis
        const rejected = card.status === 'rejected_fidelity' && showGate
        const choosable = Boolean(card.changed && card.output) && (card.status === 'accepted' || (blindGate && card.status === 'rejected_fidelity'))
        const applied = card.steps.filter((s) => s.applied).map((s) => s.module)
        const isChosen = revealed && chosen === card.variant
        return (
          <div key={card.blind_id} className="grid gap-4 lg:grid-cols-[minmax(0,2.4fr)_minmax(280px,1fr)]">
            <Card className={`relative overflow-hidden ${isChosen ? 'ring-2 ring-brand-500' : ''} ${rejected ? 'ring-2 ring-amber-500' : ''}`}>
              <div className="absolute top-2 left-2 z-10 rounded bg-black/60 px-2 py-0.5 text-[11px] font-semibold text-white">
                {name(card)}
              </div>
              {rejected && (
                <div className="absolute top-2 right-2 z-10 rounded bg-amber-500 px-2 py-0.5 text-[11px] font-semibold text-white">
                  Fermata dal controllo di fedeltà · {card.fidelity?.score.toFixed(3)} · blocco peggiore{' '}
                  {card.fidelity?.structure_local_min.toFixed(2)}
                </div>
              )}
              {card.output && card.changed ? (
                <CompareSlider before={original} after={card.output} afterLabel={card.blind_id} />
              ) : (
                <div className="flex aspect-[4/3] items-center justify-center bg-neutral-50 text-sm text-muted">
                  {card.error ? 'errore del modello' : 'lasciata com’è'}
                </div>
              )}
            </Card>

            <Card className="flex flex-col gap-3 p-4">
              <div className="flex items-baseline justify-between gap-3">
                <div>
                  <div className="text-lg leading-tight font-semibold">{name(card)}</div>
                  {revealed && <div className="mt-0.5 text-xs text-muted">{VARIANT_SUBTITLE[card.variant]}</div>}
                </div>
                {revealed && (
                  <div className="shrink-0 text-right text-[11px] text-muted tabular-nums">
                    {usd(card.cost_usd)} · {secs(card.latency_ms)}
                  </div>
                )}
              </div>
              {!revealed && (
                <p className="text-xs leading-relaxed text-muted">
                  Trascina la maniglia: a sinistra l&apos;originale, a destra questa versione. Cosa è stato corretto, da
                  chi, a che costo: lo vedi dopo la scelta.
                </p>
              )}
              {revealed && (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {d.defects.length === 0 ? (
                      <Chip tone="ok">nessun difetto</Chip>
                    ) : (
                      d.defects.map((x) => (
                        <Chip key={x} tone="brand">
                          {label(x)}
                        </Chip>
                      ))
                    )}
                    {d.advice.map((x) => (
                      <Chip key={x} tone="warn">
                        {label(x)}
                      </Chip>
                    ))}
                    {d.recommendation !== 'apply' && (
                      <Chip>{d.recommendation === 'mild' ? 'correzione leggera' : 'lascia com’è'}</Chip>
                    )}
                    {card.ai_reconstructed && <Chip tone="warn">ricostruita da AI</Chip>}
                    {card.crop_pct >= 3 && <Chip tone="warn">ritaglio {Math.round(card.crop_pct)}%</Chip>}
                  </div>
                  {d.reason && <p className="text-xs leading-relaxed text-neutral-700">{d.reason}</p>}
                  {card.measured_changes && (
                    <p className="text-[11px] text-muted">
                      Un modello generativo non dichiara scelte: le righe sotto sono <b>misurate dopo</b> sui pixel.
                    </p>
                  )}
                  <ul className="divide-y divide-line border-t border-line pt-1">
                    {MODULES.map((m) => {
                      const step = card.steps.find((s) => s.module === m) ?? {
                        module: m,
                        needed: false,
                        applied: false,
                        passed: null,
                        retried: false,
                        fidelity: null,
                        params: null,
                      }
                      return <StepRow key={m} step={step} />
                    })}
                  </ul>
                  <div className="flex items-center justify-between gap-3 border-t border-line pt-3 text-[11px] text-muted">
                    <span className="tabular-nums">
                      {applied.length ? `${applied.length} moduli` : 'nessun modulo'}
                      {card.fidelity && ` · fedeltà ${card.fidelity.score.toFixed(3)}`}
                    </span>
                    {d.plan_fixes?.length > 0 && (
                      <span className="truncate" title={d.plan_fixes.join('; ')}>
                        guardie: {d.plan_fixes.length}
                      </span>
                    )}
                    {d.review_verdict && <span>verifica: {d.review_verdict === 'adjust' ? 'corretto il piano' : 'ok'}</span>}
                  </div>
                </>
              )}
              {rejected && (
                <p className="text-xs leading-relaxed text-amber-800">
                  Fermata dal controllo di fedeltà:{' '}
                  {card.fidelity && card.fidelity.score < card.fidelity.threshold
                    ? `troppo diversa dall’originale nel complesso (${card.fidelity.score.toFixed(3)} < ${card.fidelity.threshold})`
                    : `almeno una zona è stata ridisegnata (blocco peggiore ${card.fidelity?.structure_local_min.toFixed(2)} < ${card.fidelity?.local_floor})`}
                  {blindGate ? '. Nel prodotto non sarebbe stata proposta.' : '. Si vede, non si può scegliere.'}
                </p>
              )}
              {onChoose && (
                <div className="mt-auto pt-2">
                  <Button className="w-full" disabled={!choosable} onClick={() => onChoose(card.variant)}>
                    Scelgo {name(card)}
                  </Button>
                </div>
              )}
            </Card>
          </div>
        )
      })}
      {onKeep && (
        <div className="flex justify-end">
          <Button variant="ghost" onClick={onKeep}>
            Nessuna delle tre, tengo l&apos;originale
          </Button>
        </div>
      )}
    </div>
  )
}
