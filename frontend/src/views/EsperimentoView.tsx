import { useEffect, useState } from 'react'

import { Bar, Button, Card, SectionTitle, Stat, pct, secs, usd } from '../components/ui'
import { fetchSummary, isSnapshotMode } from '../lib/api'
import { VARIANT_LABEL, VARIANT_SUBTITLE, type Summary, type SummaryRow, type VariantId } from '../types'

type State = { kind: 'loading' } | { kind: 'ready'; data: Summary } | { kind: 'error'; message: string }

const n = (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? '—' : v.toFixed(digits))
const name = (v: string) => VARIANT_LABEL[v as VariantId] ?? v

/** The results page. Every number here is computed by cv-service from the saved
 *  runs (experiments/runs) and the recorded judgements (experiments/choices.csv)
 *  each time the page opens: nothing is a static file. */
export function EsperimentoView() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  const load = () => {
    setState({ kind: 'loading' })
    fetchSummary()
      .then((data) => setState({ kind: 'ready', data }))
      .catch((err) => setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) }))
  }
  useEffect(load, [])

  if (state.kind === 'loading') return <div className="skeleton h-64 rounded-2xl" />
  if (state.kind === 'error') {
    return (
      <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-900">
        Risultati non raggiungibili: {state.message}. <Button variant="ghost" onClick={load}>Riprova</Button>
      </Card>
    )
  }

  const d = state.data
  const v = d.verdict
  const winner = v.winner ? d.variants.find((r) => r.variant === v.winner) : undefined
  const labelled = d.variants.some((r) => r.diagnosis.n_labelled > 0)

  return (
    <div className="space-y-10">
      <section>
        <SectionTitle
          eyebrow="Decisione"
          title={winner ? `Metodo consigliato: ${VARIANT_LABEL[winner.variant]}` : 'Nessuna decisione, per ora'}
          hint={`${d.runs} foto elaborate da ogni metodo · ${d.choices} giudizi raccolti nel test cieco · ${isSnapshotMode() ? 'copia statica del' : 'aggiornato alle ' + new Date(d.generated_at * 1000).toLocaleTimeString('it-IT') + ' del'} ${new Date(d.generated_at * 1000).toLocaleDateString('it-IT')}`}
          right={<Button variant="ghost" onClick={load}>Aggiorna</Button>}
        />
        <Card className="p-5">
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Giudizi raccolti" value={`${d.choices} / ${v.min_choices}`} sub="minimo richiesto prima di prendere una decisione" />
            <Stat
              label="Giudizi «pari»"
              value={d.choices ? pct((d.ties ?? 0) / d.choices) : '—'}
              sub="coppie in cui il valutatore non ha visto differenze"
            />
            <Stat label="Metodo consigliato" value={winner ? winner.variant : '—'} sub={winner ? VARIANT_SUBTITLE[winner.variant] : v.reason} />
            <Stat
              label="Costo e tempo del consigliato"
              value={winner ? usd(winner.cost_mean_usd) : '—'}
              sub={winner ? `per foto · tempo mediano ${secs(winner.latency_p50_ms)}, 95° percentile ${secs(winner.latency_p95_ms)}` : ''}
            />
          </div>
          <p className="mt-5 border-t border-neutral-100 pt-4 text-sm leading-relaxed">{v.reason}</p>
          {v.excluded.length > 0 && (
            <p className="mt-2 text-sm text-amber-800">
              Non ammessi alla decisione: {v.excluded.map((e) => `${name(e.variant)} (${e.why})`).join('; ')}.
            </p>
          )}
          <div className="mt-4 text-xs font-semibold tracking-wide text-muted uppercase">Regola di decisione</div>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm leading-relaxed text-neutral-700">
            {d.decision_rule.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ol>
        </Card>
      </section>

      <section>
        <SectionTitle
          eyebrow="Qualità percepita"
          title="Preferenza degli utenti nel test cieco"
          hint="Un valutatore vede l'originale e due versioni corrette senza sapere quale metodo le ha prodotte, e indica quale userebbe come copertina. Ogni metodo compare in più coppie: qui la quota di coppie vinte. L'intervallo di confidenza al 95% dice quanto il dato è affidabile con questo campione."
        />
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-neutral-200 text-left text-xs tracking-wide text-muted uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Metodo</th>
                <th className="px-4 py-3 font-medium">Coppie vinte</th>
                <th className="px-4 py-3 font-medium">Coppie giocate</th>
                <th className="px-4 py-3 font-medium">Preferenza</th>
                <th className="px-4 py-3 font-medium">Intervallo di confidenza 95%</th>
              </tr>
            </thead>
            <tbody>
              {d.variants.map((r: SummaryRow) => (
                <tr key={r.variant} className={`border-b border-neutral-100 last:border-0 ${r.variant === v.winner ? 'bg-brand-50/40' : ''}`}>
                  <td className="px-4 py-3">
                    <div className="font-medium">{VARIANT_LABEL[r.variant]}</div>
                    <div className="text-xs text-muted">{VARIANT_SUBTITLE[r.variant]}</div>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{r.chosen}</td>
                  <td className="px-4 py-3 tabular-nums">{r.shown}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {r.choice_share === null ? '—' : pct(r.choice_share)}
                    <Bar value={r.choice_share ?? 0} />
                  </td>
                  <td className="px-4 py-3 text-xs text-muted tabular-nums">
                    {r.shown ? `${pct(r.choice_ci[0])} – ${pct(r.choice_ci[1])}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>

      <section>
        <SectionTitle
          eyebrow="Costo, tempo, affidabilità, rischio"
          title="Gli altri parametri di confronto"
          hint="Misurati su tutte le foto elaborate, non solo su quelle giudicate. Il controllo di fedeltà è un requisito, non un punteggio: un metodo che lo supera di rado non entra nella decisione."
        />
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-neutral-200 text-left text-xs tracking-wide text-muted uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Metodo</th>
                <th className="px-4 py-3 font-medium">Foto</th>
                <th className="px-4 py-3 font-medium">Costo per foto</th>
                <th className="px-4 py-3 font-medium">Tempo mediano / 95°</th>
                <th className="px-4 py-3 font-medium">Errori</th>
                <th className="px-4 py-3 font-medium">Piani corretti dal sistema</th>
                <th className="px-4 py-3 font-medium">Bocciati dal controllo di fedeltà</th>
                <th className="px-4 py-3 font-medium">Fedeltà minima</th>
                <th className="px-4 py-3 font-medium">Lascia l’originale</th>
                {labelled && <th className="px-4 py-3 font-medium">Diagnosi: precisione / richiamo / F1</th>}
              </tr>
            </thead>
            <tbody>
              {d.variants.map((r) => (
                <tr key={r.variant} className="border-b border-neutral-100 last:border-0">
                  <td className="px-4 py-3 font-medium">{VARIANT_LABEL[r.variant]}</td>
                  <td className="px-4 py-3 tabular-nums">{r.runs}</td>
                  <td className="px-4 py-3 tabular-nums">{usd(r.cost_mean_usd)}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {secs(r.latency_p50_ms)} / {secs(r.latency_p95_ms)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{pct(r.error_rate)}</td>
                  <td className="px-4 py-3 tabular-nums">{pct(r.fixes_rate)}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {pct(r.gate_rejected_rate)}
                    <Bar value={r.gate_rejected_rate} tone="warn" />
                  </td>
                  <td className="px-4 py-3 tabular-nums">{n(r.fidelity_min, 3)}</td>
                  <td className="px-4 py-3 tabular-nums">{pct(r.keep_original_rate + r.unchanged_rate)}</td>
                  {labelled && (
                    <td className="px-4 py-3 text-xs tabular-nums">
                      {r.diagnosis.n_labelled && r.diagnosis.precision !== null
                        ? `${n(r.diagnosis.precision, 2)} / ${n(r.diagnosis.recall, 2)} / ${n(r.diagnosis.f1, 2)} (n=${r.diagnosis.n_labelled})`
                        : 'non diagnostica'}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <dl className="mt-3 grid gap-x-8 gap-y-1.5 text-xs leading-relaxed text-muted sm:grid-cols-2">
          <div>
            <dt className="inline font-medium text-neutral-700">Costo per foto: </dt>
            <dd className="inline">token dei modelli a prezzo di listino più il tempo di GPU su Replicate; le regole non chiamano modelli.</dd>
          </div>
          <div>
            <dt className="inline font-medium text-neutral-700">Errori: </dt>
            <dd className="inline">risposte del modello non leggibili o servizio non raggiunto; in quei casi il prodotto ricade sulle regole.</dd>
          </div>
          <div>
            <dt className="inline font-medium text-neutral-700">Piani corretti dal sistema: </dt>
            <dd className="inline">quante volte una guardia deterministica ha modificato il piano del modello (rotazione misurata usata al posto della sua, verso dell’esposizione invertito, contrasto locale spento su foto compresse).</dd>
          </div>
          <div>
            <dt className="inline font-medium text-neutral-700">Bocciati dal controllo di fedeltà: </dt>
            <dd className="inline">quota di correzioni fermate perché l’immagine si allontanava troppo dall’originale, anche dopo un secondo tentativo più prudente.</dd>
          </div>
          <div>
            <dt className="inline font-medium text-neutral-700">Diagnosi: </dt>
            <dd className="inline">difetti individuati confrontati con l’etichettatura manuale del dataset (precisione = quanti dei difetti segnalati sono veri; richiamo = quanti dei difetti veri sono stati trovati).</dd>
          </div>
          <div>
            <dt className="inline font-medium text-neutral-700">Lascia l’originale: </dt>
            <dd className="inline">quota di foto in cui il metodo ha deciso di non correggere nulla.</dd>
          </div>
        </dl>
      </section>
    </div>
  )
}
