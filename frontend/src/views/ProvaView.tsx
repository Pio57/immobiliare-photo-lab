import { useEffect, useState } from 'react'

import { Dropzone } from '../components/Dropzone'
import { Lightbox } from '../components/Lightbox'
import { Button, Card, SectionTitle, secs } from '../components/ui'
import { VersionGrid } from '../components/VersionCards'
import { isLiveConfigured, pendingUpload, runProduct, waitForResult } from '../lib/api'
import { VARIANT_LABEL, type ProductResponse, type VersionCard } from '../types'

type State =
  | { kind: 'idle' }
  | { kind: 'running'; preview: string; elapsedMs: number }
  | { kind: 'done'; preview: string; response: ProductResponse }
  | { kind: 'error'; message: string }

/** The product: one photo in, the three methods side by side with their sheets.
 *  Nothing to choose here; the preference is measured in the Studio view. */
export function ProvaView() {
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [zoom, setZoom] = useState<VersionCard | null>(null)

  // After a reload, pick up the upload that was in flight instead of asking for the photo again.
  useEffect(() => {
    const pending = pendingUpload()
    if (!pending || state.kind !== 'idle') return
    setState({ kind: 'running', preview: '', elapsedMs: Date.now() - pending.t0 })
    waitForResult(pending.image_id, (elapsedMs) => setState((s) => (s.kind === 'running' ? { ...s, elapsedMs } : s)))
      .then((response) => setState({ kind: 'done', preview: response.original ?? '', response }))
      .catch((err) => setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onFile = async (file: File) => {
    const preview = URL.createObjectURL(file)
    setState({ kind: 'running', preview, elapsedMs: 0 })
    try {
      const response = await runProduct(file, (elapsedMs) => setState((s) => (s.kind === 'running' ? { ...s, elapsedMs } : s)))
      setState({ kind: 'done', preview: response.original ?? preview, response })
    } catch (err) {
      setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }

  if (!isLiveConfigured()) {
    return (
      <Card className="p-5 text-sm">
        <p className="font-medium">Vista Prova disabilitata</p>
        <p className="mt-1 text-muted">
          La Prova ha bisogno del backend (n8n + cv-service) acceso. Studio ed Esperimento funzionano comunque sulla copia statica dei risultati.
        </p>
      </Card>
    )
  }

  if (state.kind === 'idle' || state.kind === 'error') {
    return (
      <div className="mx-auto max-w-3xl space-y-6 pt-6">
        <div className="text-center">
          <div className="mb-2 text-xs font-semibold text-brand-500">Prima di pubblicare l&apos;annuncio</div>
          <h2 className="text-[36px] leading-[1.1] font-bold tracking-tight">Le foto giuste per l&apos;annuncio, con un click.</h2>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-neutral-600">
            Carica una foto scattata col telefono. Tre metodi la correggono in parallelo (regole, modello con verifica,
            generativo), con lo stesso controllo di fedeltà. Per ciascuno vedi il risultato, cosa ha visto e cosa ha fatto.
          </p>
        </div>
        {state.kind === 'error' && <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-900">{state.message}</Card>}
        <Dropzone onFile={onFile} />
      </div>
    )
  }

  if (state.kind === 'running') {
    return (
      <div className="space-y-5">
        <div className="flex items-center gap-5">
          {state.preview ? (
            <img src={state.preview} alt="Originale" className="h-24 w-32 rounded-md object-cover" />
          ) : (
            <div className="skeleton h-24 w-32 rounded-md" />
          )}
          <div>
            <p className="font-medium">Tre correzioni in corso… {Math.round(state.elapsedMs / 1000)} s</p>
            <p className="text-sm text-muted">
              Regole (~15 s), modello con verifica (~25 s), generativo (30 s, fino a 2 min se il modello è freddo). Stesso
              controllo di fedeltà per tutte.
            </p>
          </div>
        </div>
        <div className="grid gap-5 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton aspect-[3/4] rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  const r = state.response

  return (
    <div className="space-y-6">
      {zoom && zoom.output && (
        <Lightbox
          title={VARIANT_LABEL[zoom.variant]}
          subtitle={zoom.steps.filter((s) => s.applied).map((s) => s.module).join(' + ') || (zoom.measured_changes ? 'immagine rigenerata' : 'nessun modulo')}
          before={state.preview}
          after={zoom.output}
          afterLabel={VARIANT_LABEL[zoom.variant].split(' · ')[1]}
          onClose={() => setZoom(null)}
        />
      )}

      <section>
        <SectionTitle
          eyebrow="Stessa foto, tre metodi"
          title="Cosa ha fatto ogni metodo"
          hint="Trascina la maniglia su ogni immagine: a sinistra l’originale, a destra la versione. Sotto, la scheda: come decide il metodo, cosa ha visto, quali moduli ha eseguito e con quali valori, tempo di elaborazione."
          right={
            <Button variant="ghost" onClick={() => setState({ kind: 'idle' })}>
              Un&apos;altra foto
            </Button>
          }
        />
        <VersionGrid cards={r.cards} original={state.preview} onZoom={setZoom} />
        <p className="mt-3 text-xs text-muted tabular-nums">Risposta completa in {secs(r.latency_ms)}.</p>
      </section>
    </div>
  )
}
