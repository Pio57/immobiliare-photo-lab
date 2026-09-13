import { useEffect, useState } from 'react'

import { Dropzone } from '../components/Dropzone'
import { Lightbox } from '../components/Lightbox'
import { Button, Card, SectionTitle, secs, usd } from '../components/ui'
import { VersionStack, label } from '../components/VersionCards'
import { isLiveConfigured, pendingUpload, runProduct, sendChoice, waitForResult } from '../lib/api'
import { VARIANT_LABEL, type ProductResponse, type VariantId, type VersionCard } from '../types'

type State =
  | { kind: 'idle' }
  | { kind: 'running'; preview: string; elapsedMs: number }
  | { kind: 'done'; preview: string; response: ProductResponse; chosen: VariantId | null | undefined; saved: boolean }
  | { kind: 'error'; message: string }

export function ProvaView() {
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [zoom, setZoom] = useState<VersionCard | null>(null)

  // After a reload, pick up the upload that was in flight instead of asking for the photo again.
  useEffect(() => {
    const pending = pendingUpload()
    if (!pending || state.kind !== 'idle') return
    setState({ kind: 'running', preview: '', elapsedMs: Date.now() - pending.t0 })
    waitForResult(pending.image_id, (elapsedMs) => setState((s) => (s.kind === 'running' ? { ...s, elapsedMs } : s)))
      .then((response) => setState({ kind: 'done', preview: response.original ?? '', response, chosen: undefined, saved: false }))
      .catch((err) => setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onFile = async (file: File) => {
    const preview = URL.createObjectURL(file)
    setState({ kind: 'running', preview, elapsedMs: 0 })
    try {
      const response = await runProduct(file, (elapsedMs) =>
        setState((s) => (s.kind === 'running' ? { ...s, elapsedMs } : s)),
      )
      setState({ kind: 'done', preview: response.original ?? preview, response, chosen: undefined, saved: false })
    } catch (err) {
      setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }

  const choose = async (chosen: VariantId | null) => {
    if (state.kind !== 'done') return
    setState({ ...state, chosen })
    try {
      await sendChoice({
        image_id: state.response.image_id,
        chosen,
        shown: state.response.cards.filter((c) => c.changed && c.output && c.status === 'accepted').map((c) => c.variant),
        order: state.response.order,
      })
      setState((s) => (s.kind === 'done' ? { ...s, chosen, saved: true } : s))
    } catch {
      /* the choice is still shown; only the tally misses it */
    }
  }

  if (!isLiveConfigured()) {
    return (
      <Card className="p-5 text-sm">
        <p className="font-medium">Vista Prova disabilitata</p>
        <p className="mt-1 text-muted">
          La Prova ha bisogno del backend (n8n + cv-service) acceso. Studio ed Esperimento funzionano comunque sulla
          copia statica dei risultati.
        </p>
      </Card>
    )
  }

  if (state.kind === 'idle' || state.kind === 'error') {
    return (
      <div className="mx-auto max-w-3xl space-y-6 pt-6">
        <div className="text-center">
          <div className="mb-3 text-[11px] font-semibold tracking-[0.14em] text-brand-500 uppercase">
            Prima di pubblicare l&apos;annuncio
          </div>
          <h2 className="font-display text-5xl leading-[1.05] font-medium">La copertina giusta, con un click.</h2>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-neutral-600">
            Carica la foto scattata col telefono. Tre versioni corrette da tre metodi diversi — regole, modello con
            verifica, generativo — tutte passate dallo stesso controllo di fedeltà. Scegli la migliore: la tua scelta è
            la misura.
          </p>
        </div>
        {state.kind === 'error' && (
          <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-900">{state.message}</Card>
        )}
        <Dropzone onFile={onFile} />
      </div>
    )
  }

  if (state.kind === 'running') {
    return (
      <div className="space-y-5">
        <div className="flex items-center gap-5">
          {state.preview ? (
            <img src={state.preview} alt="Originale" className="h-24 w-32 rounded-lg object-cover" />
          ) : (
            <div className="skeleton h-24 w-32 rounded-lg" />
          )}
          <div>
            <p className="font-medium">Tre correzioni in corso… {Math.round(state.elapsedMs / 1000)} s</p>
            <p className="text-sm text-muted">
              Regole (~15 s), Haiku con verifica (~25 s), generativo (30 s, fino a 2 min se il modello è freddo). Stesso
              gate per tutte.
            </p>
          </div>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton aspect-[3/4] rounded-2xl" />
          ))}
        </div>
      </div>
    )
  }

  const r = state.response
  const revealed = state.chosen !== undefined
  const chosenCard = r.cards.find((c) => c.variant === state.chosen)

  return (
    <div className="space-y-8">
      {zoom && zoom.output && (
        <Lightbox
          title={revealed ? VARIANT_LABEL[zoom.variant] : `Versione ${zoom.blind_id.slice(1)}`}
          subtitle={zoom.steps.filter((s) => s.applied).map((s) => s.module).join(' + ') || 'nessun modulo'}
          before={state.preview}
          after={zoom.output}
          afterLabel={zoom.blind_id}
          onClose={() => setZoom(null)}
        />
      )}

      {r.input_warnings.some((w) => !w.startsWith('letterbox')) && (
        <Card className="border-amber-300 bg-amber-50 p-4 text-sm">
          <b>Foto a bassa qualità in ingresso</b> (
          {r.input_warnings
            .filter((w) => !w.startsWith('letterbox'))
            .map((w) => label(w.split(':')[0]))
            .join(', ')}
          ). Nessuna pipeline ricostruisce dettagli che non ci sono: se puoi, carica l&apos;originale dalla galleria.
          {r.input_warnings.some((w) => w.startsWith('letterbox')) && ' Rimosse le bande nere ai bordi.'}
        </Card>
      )}

      <section>
        <SectionTitle
          eyebrow={revealed ? 'Scelta registrata' : 'Tre versioni, alla cieca'}
          title={
            !revealed
              ? 'Quale useresti come copertina?'
              : state.chosen === null
                ? 'Tieni l’originale'
                : `Hai scelto ${chosenCard ? VARIANT_LABEL[chosenCard.variant] : ''}`
          }
          hint={
            !revealed
              ? 'Stessa foto, tre metodi diversi, stesso gate. I nomi compaiono dopo la scelta, per non farsi influenzare.'
              : state.saved
                ? 'La scelta è nel tabellone (vista Esperimento). I nomi dei workflow sono ora visibili.'
                : 'Scelta registrata localmente.'
          }
          right={
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setState({ kind: 'idle' })}>
                Un&apos;altra foto
              </Button>
            </div>
          }
        />
        <VersionStack
          cards={r.cards}
          original={state.preview}
          revealed={revealed}
          chosen={state.chosen}
          onChoose={!revealed ? (v) => void choose(v) : undefined}
          onKeep={!revealed ? () => void choose(null) : undefined}
        />
        <p className="mt-3 text-xs text-muted tabular-nums">
          Risposta in {secs(r.latency_ms)} · costo totale {usd(r.cards.reduce((a, c) => a + c.cost_usd, 0))} per le
          tre versioni.
        </p>
      </section>
    </div>
  )
}
