import { useEffect, useState } from 'react'

import { Bar, Button, Card, SectionTitle, Stat, pct, secs, usd } from '../components/ui'
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
            <Stat label="Costo del consigliato" value={winner ? usd(winner.cost_mean_usd) : '·'} sub={winner ? `per foto · ${secs(winner.latency_p50_ms)} mediano` : ''} />
          </div>
          <p className="mt-5 border-t border-neutral-100 pt-4 text-sm leading-relaxed">{v.reason}</p>
          {v.excluded.length > 0 && (
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
          hint="Ogni valutatore, nella vista Studio, risponde senza sapere quale metodo ha prodotto cosa. Realismo: originale accanto a una versione, «vedi elementi finti o diversi?». Qualità: la sola versione, voto da 1 a 5. Foto migliore: originale in alto e le versioni affiancate, «quale useresti?». Output efficace: calcolato dalle etichette manuali dei difetti, senza valutatori."
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
                    <div className="mt-1 text-xs text-muted">{r.effective_n ? `su ${r.effective_n} foto etichettate` : 'nessuna etichetta'}</div>
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
            <thead className="border-b border-line text-left text-xs text-muted">
              <tr>
                <th className={th}>Metodo</th>
                <th className={th}>Foto</th>
                <th className={th}>Costo per foto</th>
                <th className={th}>Tempo mediano / 95°</th>
                <th className={th}>Errori</th>
                <th className={th}>Piani corretti dal sistema</th>
                <th className={th}>Fermati dal controllo di fedeltà</th>
                <th className={th}>Fedeltà minima</th>
                <th className={th}>Lascia l’originale</th>
                <th className={th}>Diagnosi · precisione / richiamo</th>
              </tr>
            </thead>
            <tbody>
              {d.variants.map((r) => (
                <tr key={r.variant} className="border-b border-neutral-100 last:border-0">
                  <td className={`${td} font-semibold`}>{VARIANT_LABEL[r.variant]}</td>
                  <td className={td}>{r.runs}</td>
                  <td className={td}>{usd(r.cost_mean_usd)}</td>
                  <td className={td}>
                    {secs(r.latency_p50_ms)} / {secs(r.latency_p95_ms)}
                  </td>
                  <td className={td}>{pct(r.error_rate)}</td>
                  <td className={td}>{pct(r.fixes_rate)}</td>
                  <td className={td}>
                    {pct(r.gate_rejected_rate)}
                    <Bar value={r.gate_rejected_rate} tone="warn" />
                  </td>
                  <td className={td}>{n(r.fidelity_min, 3)}</td>
                  <td className={td}>{pct(r.keep_original_rate + r.unchanged_rate)}</td>
                  <td className={`${td} text-xs`}>
                    {r.diagnosis.n_labelled && r.diagnosis.precision !== null
                      ? `${pct(r.diagnosis.precision)} / ${pct(r.diagnosis.recall ?? 0)} (n=${r.diagnosis.n_labelled})`
                      : 'non diagnostica'}
                  </td>
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
            <dt className="inline font-medium text-neutral-700">Fermati dal controllo di fedeltà: </dt>
            <dd className="inline">quota di correzioni bloccate perché l’immagine si allontanava troppo dall’originale, anche dopo un secondo tentativo più prudente.</dd>
          </div>
          <div>
            <dt className="inline font-medium text-neutral-700">Diagnosi: </dt>
            <dd className="inline">difetti individuati confrontati con l’etichettatura manuale (precisione = quanti dei difetti segnalati sono veri; richiamo = quanti dei difetti veri sono stati trovati).</dd>
          </div>
          <div>
            <dt className="inline font-medium text-neutral-700">Output efficace: </dt>
            <dd className="inline">foto in cui ogni difetto etichettato a mano è stato trattato dal modulo competente, nessuna correzione è stata fermata e il metodo non ha fallito: pubblicabile senza altro ritocco. La compressione è una condizione dell’input (il piano diventa più prudente), non un difetto da risolvere.</dd>
          </div>
        </dl>
      </section>
    </div>
  )
}
