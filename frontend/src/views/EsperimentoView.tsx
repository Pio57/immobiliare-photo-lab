import { useEffect, useState } from 'react'

import { Bar, Button, Card, SectionTitle, Stat, pct } from '../components/ui'
import { fetchSummary, isSnapshotMode } from '../lib/api'
import { VARIANT_LABEL, VARIANT_SUBTITLE, type Summary, type SummaryRow, type VariantId } from '../types'

type State = { kind: 'loading' } | { kind: 'ready'; data: Summary } | { kind: 'error'; message: string }

const n = (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? '·' : v.toFixed(digits))
const share = (v: number | null | undefined) => (v === null || v === undefined ? '·' : pct(v))
const name = (v: string) => VARIANT_LABEL[v as VariantId] ?? v
const th = 'px-4 py-3 font-medium'
const td = 'px-4 py-3 align-top tabular-nums'

function Method({ r, winner }: { r: SummaryRow; winner: boolean }) {
  return (
    <td className={`${td} min-w-52`}>
      <div className="flex items-center gap-2 font-semibold">
        {VARIANT_LABEL[r.variant]}
        {winner && <span className="rounded bg-brand-50 px-1.5 py-0.5 text-[11px] font-semibold text-brand-600">consigliato</span>}
      </div>
      <div className="mt-0.5 text-xs leading-snug text-muted">{VARIANT_SUBTITLE[r.variant]}</div>
    </td>
  )
}

/** The results page. Every number here is computed by cv-service from the saved
 *  runs (experiments/runs) and the recorded judgements (experiments/judgments.csv)
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

  if (state.kind === 'loading') return <div className="skeleton h-64 rounded-lg" />
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
  const when = new Date(d.generated_at * 1000)

  return (
    <div className="space-y-10">
      <section>
        <SectionTitle
          eyebrow="Esperimento · fase 1, sul prototipo"
          title={winner ? `Metodo consigliato: ${VARIANT_LABEL[winner.variant]}` : 'Nessuna decisione, per ora'}
          hint={`${d.runs} foto elaborate da ogni metodo · ${d.judgments} risposte da ${d.testers} valutator${d.testers === 1 ? 'e' : 'i'} · ${isSnapshotMode() ? 'copia statica del' : 'aggiornato alle ' + when.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) + ' del'} ${when.toLocaleDateString('it-IT')}`}
          right={<Button variant="ghost" onClick={load}>Aggiorna</Button>}
        />
        <Card className="p-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Giudizi «foto migliore»" value={`${d.choices} / ${v.min_choices}`} sub="raccolti / minimo richiesto per decidere" />
            <Stat label="Terrebbero l’originale" value={share(d.keep_original_share)} sub="quota di giudizi in cui nessuna versione convince" />
            <Stat label="Metodo consigliato" value={winner ? winner.variant : '·'} sub={winner ? VARIANT_SUBTITLE[winner.variant] : 'in attesa dei giudizi'} />
            <Stat label="Valutatori" value={d.testers} sub={`${d.judgments} risposte in tutto`} />
          </div>
          <p className="mt-5 border-t border-neutral-100 pt-4 text-sm leading-relaxed">{v.reason}</p>
          {d.choices > 0 && v.excluded.length > 0 && (
            <p className="mt-2 text-sm text-amber-800">
              Non ammessi alla decisione: {v.excluded.map((e) => `${name(e.variant)} (${e.why})`).join('; ')}.
            </p>
          )}
          <div className="mt-4 text-xs font-semibold text-muted">Regola di decisione, fissata prima di guardare i dati</div>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm leading-relaxed text-neutral-700">
            {d.decision_rule.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ol>
        </Card>
      </section>

      <section>
        <SectionTitle
          eyebrow="Elementi qualitativi"
          title="Le quattro misure del test cieco"
          hint="Ogni valutatore, nella vista Studio, risponde senza sapere quale metodo ha prodotto cosa. Realismo: originale accanto a una versione, «vedi elementi finti o diversi?». Qualità: la sola versione, voto da 1 a 5. Foto migliore: originale in alto e le versioni affiancate, «quale useresti?». Output efficace: la versione è pubblicabile così com’è, cioè voto almeno 4 e nessuna alterazione vista dallo stesso valutatore."
        />
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs text-muted">
              <tr>
                <th className={th}>Metodo</th>
                <th className={th}>Realismo · tasso di alterazione</th>
                <th className={th}>Qualità · voto medio (1–5)</th>
                <th className={th}>Foto migliore · quota di vittorie</th>
                <th className={th}>Output efficace · foto pubblicabili</th>
              </tr>
            </thead>
            <tbody>
              {d.variants.map((r) => (
                <tr key={r.variant} className={`border-b border-neutral-100 last:border-0 ${r.variant === v.winner ? 'bg-brand-50/40' : ''}`}>
                  <Method r={r} winner={r.variant === v.winner} />
                  <td className={td}>
                    {share(r.alteration_rate)}
                    <Bar value={r.alteration_rate ?? 0} tone="warn" />
                    <div className="mt-1 text-xs text-muted">
                      {r.realism_n ? `${r.altered} «sì» su ${r.realism_n} · IC 95% ${pct(r.alteration_ci[0])}–${pct(r.alteration_ci[1])}` : 'nessuna risposta'}
                    </div>
                  </td>
                  <td className={td}>
                    {n(r.mos, 2)}
                    <Bar value={r.mos ? (r.mos - 1) / 4 : 0} tone="ok" />
                    <div className="mt-1 text-xs text-muted">{r.quality_n ? `${r.quality_n} voti${r.mos_sd !== null ? ` · deviazione ${n(r.mos_sd, 2)}` : ''} · sopra 3,5 è buona` : 'nessun voto'}</div>
                  </td>
                  <td className={td}>
                    {share(r.choice_share)}
                    <Bar value={r.choice_share ?? 0} />
                    <div className="mt-1 text-xs text-muted">
                      {r.shown ? `${r.chosen} su ${r.shown} · IC 95% ${pct(r.choice_ci[0])}–${pct(r.choice_ci[1])}` : 'nessun giudizio'}
                    </div>
                  </td>
                  <td className={td}>
                    {share(r.effective_rate)}
                    <Bar value={r.effective_rate ?? 0} tone="ok" />
                    <div className="mt-1 text-xs text-muted">{r.effective_n ? `su ${r.effective_n} valutazioni` : 'nessuna valutazione'}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>

    </div>
  )
}
