import { CompareSlider } from './CompareSlider'
import { Button, Card, secs } from './ui'
import { DEFECT_LABEL, VARIANT_LABEL, VARIANT_SUBTITLE, type ModuleName, type Step, type VersionCard } from '../types'

const MODULES: ModuleName[] = ['Risoluzione', 'Colore', 'Luce', 'Pulizia', 'Raddrizza', 'Nitidezza']

export const label = (d: string) => DEFECT_LABEL[d] ?? d.replace(/_/g, ' ')

/** How each method decides, in the agent's words. */
const HOW: Record<VersionCard['variant'], string> = {
  D1: 'Nessun modello: luminosità, colore, rumore e linee vengono misurati e regole scritte a mano scelgono le correzioni.',
  D2: 'Un modello di visione guarda la foto e le misure, indica i difetti e i valori; poi riguarda il risultato e, se serve, corregge il piano.',
  D3: 'Un modello generativo riceve la foto e un prompt da fotografo e restituisce una nuova immagine della stessa stanza.',
}

export function Chip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'warn' | 'ok' | 'brand' }) {
  const style = {
    neutral: 'bg-neutral-100 text-neutral-700 ring-neutral-500/15',
    warn: 'bg-amber-50 text-amber-800 ring-amber-600/25',
    ok: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    brand: 'bg-brand-50 text-brand-600 ring-brand-500/25',
  }[tone]
  return <span className={`inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${style}`}>{children}</span>
}

/** One correction module: ran / stopped / not needed. */
function StepRow({ step }: { step: Step }) {
  const state = !step.needed ? 'idle' : step.applied ? 'applied' : 'skipped'
  const dot = { idle: 'bg-neutral-300', applied: 'bg-brand-500', skipped: 'bg-neutral-400' }[state]
  const params = step.params
    ? Object.entries(step.params)
        .filter(([k, v]) => v !== 0 && v !== 1 && k !== 'latency_ms' && k !== 'cost_usd' && v !== undefined)
        .map(([k, v]) =>
          k === 'plan_adjusted' ? `piano adattato: ${v}` : k === 'crop_pct' ? `ritaglio ${Math.round(Number(v))}%` : `${k} ${typeof v === 'number' ? +v.toFixed(2) : v}`,
        )
        .join(' · ')
    : ''
  return (
    <li className={`flex items-baseline gap-2 py-1 text-xs ${state === 'idle' ? 'opacity-45' : ''}`}>
      <span className={`h-2 w-2 shrink-0 translate-y-[-1px] rounded-full ${dot}`} />
      <span className="w-20 shrink-0 font-medium">{step.module}</span>
      <span className="min-w-0 flex-1 truncate text-neutral-700" title={params}>
        {state === 'idle' ? 'non necessario' : state === 'skipped' ? 'non applicato' : params || 'applicato'}
        {step.retried && state === 'applied' && ' · 2º tentativo'}
      </span>
    </li>
  )
}

/** A generative output in the rows of the modules, from the after-the-fact measurements. */
function measuredRows(m: Record<string, number>): [string, string][] {
  const sign = (v: number, unit = '') => `${v > 0 ? '+' : ''}${v}${unit}`
  return [
    ['Colore', `dominante ${m.cast_before} → ${m.cast_after}`],
    ['Luce', `luminosità ${sign(m.luminance_delta)} · contrasto ${sign(m.contrast_delta)}`],
    ['Pulizia', `rumore ${m.noise_before} → ${m.noise_after}`],
    ['Raddrizza', `inclinazione ${m.tilt_before}° → ${m.tilt_after}°`],
    ['Nitidezza', `×${m.sharpness_ratio} rispetto all’originale`],
    ['Risoluzione', `scala ×${m.scale}`],
  ]
}

/** The three versions side by side, each with its own before/after handle and,
 *  below, the sheet of what that method did: how it decides, what it found, which
 *  modules ran with which values, cost and time. Nothing to choose here: the Prova
 *  view shows the outputs, the Studio view measures the preference. */
export function VersionGrid({ cards, original, onZoom }: { cards: VersionCard[]; original: string; onZoom?: (card: VersionCard) => void }) {
  const ordered = [...cards].sort((a, b) => a.variant.localeCompare(b.variant))
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      {ordered.map((card, i) => {
        const d = card.diagnosis
        const applied = card.steps.filter((s) => s.applied).map((s) => s.module)
        return (
          <div key={card.variant} className="flex flex-col gap-3">
            <Card className="relative overflow-hidden">
              <div className="absolute top-2 left-2 z-10 rounded bg-black/60 px-2 py-0.5 text-[11px] font-semibold text-white">
                Versione {i + 1} · {VARIANT_LABEL[card.variant].split(' · ')[1]}
              </div>
              {card.output && card.changed ? (
                <CompareSlider before={original} after={card.output} afterLabel={`V${i + 1}`} />
              ) : (
                <div className="flex aspect-[4/3] items-center justify-center bg-neutral-50 text-sm text-muted">
                  {card.error ? 'errore del modello' : 'lasciata com’è'}
                </div>
              )}
            </Card>

            <Card className="flex flex-1 flex-col gap-3 p-4">
              <div>
                <div className="text-base leading-tight font-semibold">{VARIANT_LABEL[card.variant]}</div>
                <div className="mt-0.5 text-xs text-muted">{VARIANT_SUBTITLE[card.variant]}</div>
              </div>
              <p className="text-xs leading-relaxed text-neutral-700">{HOW[card.variant]}</p>

              <div className="border-t border-line pt-3">
                <div className="mb-1.5 text-[11px] font-semibold text-muted">Cosa ha visto</div>
                <div className="flex flex-wrap gap-1.5">
                  {card.variant === 'D3' ? (
                    <Chip>non diagnostica: ridisegna tutto</Chip>
                  ) : d.defects.length === 0 ? (
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
                  {d.recommendation !== 'apply' && <Chip>{d.recommendation === 'mild' ? 'correzione leggera' : 'lascia com’è'}</Chip>}
                  {card.ai_reconstructed && <Chip tone="warn">ricostruita da AI</Chip>}
                  {card.crop_pct >= 3 && <Chip tone="warn">ritaglio {Math.round(card.crop_pct)}%</Chip>}
                </div>
                {d.reason && <p className="mt-2 text-xs leading-relaxed text-neutral-700">{d.reason}</p>}
              </div>

              <div className="border-t border-line pt-3">
                <div className="mb-1 text-[11px] font-semibold text-muted">Cosa ha fatto</div>
                {card.measured_changes ? (
                  <>
                    <p className="text-xs leading-relaxed text-neutral-700">
                      Immagine rigenerata in un colpo solo, senza moduli. Differenze rispetto all’originale misurate dopo, sui pixel:
                    </p>
                    <ul className="mt-1 divide-y divide-neutral-100">
                      {measuredRows(card.measured_changes).map(([k, v]) => (
                        <li key={k} className="flex items-baseline gap-2 py-1 text-xs">
                          <span className="h-2 w-2 shrink-0 translate-y-[-1px] rounded-full bg-brand-500" />
                          <span className="w-20 shrink-0 font-medium">{k}</span>
                          <span className="min-w-0 flex-1 truncate text-neutral-700">{v}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <ul className="divide-y divide-neutral-100">
                    {MODULES.map((m) => {
                      const step = card.steps.find((s) => s.module === m) ?? { module: m, needed: false, applied: false, passed: null, retried: false, fidelity: null, params: null }
                      return <StepRow key={m} step={step} />
                    })}
                  </ul>
                )}
              </div>

              <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-[11px] text-muted tabular-nums">
                <span>
                  {card.measured_changes ? 'immagine rigenerata' : applied.length ? `${applied.length} moduli` : 'nessun modulo'}
                  {card.fidelity && ` · fedeltà ${card.fidelity.score.toFixed(3)}`}
                </span>
                <span>{secs(card.latency_ms)}</span>
                {d.plan_fixes?.length > 0 && (
                  <span className="w-full truncate" title={d.plan_fixes.join('; ')}>
                    guardie del sistema: {d.plan_fixes.length}
                  </span>
                )}
                {d.review_verdict && <span className="w-full">verifica: {d.review_verdict === 'adjust' ? 'ha corretto il piano' : 'confermato'}</span>}
              </div>
              {onZoom && card.output && card.changed && (
                <Button variant="ghost" onClick={() => onZoom(card)}>
                  Ingrandisci il confronto
                </Button>
              )}
            </Card>
          </div>
        )
      })}
    </div>
  )
}
