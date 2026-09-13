import { useState } from 'react'

import { EsperimentoView } from './views/EsperimentoView'
import { ProvaView } from './views/ProvaView'
import { StudioView } from './views/StudioView'

type View = 'prova' | 'studio' | 'esperimento'

/** The product first; the two lab views sit together, so the hierarchy on
 *  screen matches the one in the case study. */
const NAV: { id: View; label: string; hint: string }[] = [
  { id: 'prova', label: 'Prova', hint: 'il prodotto, sulla tua foto' },
  { id: 'studio', label: 'Studio', hint: 'test cieco sulle 24 foto' },
  { id: 'esperimento', label: 'Esperimento', hint: 'risultati e decisione' },
]

const initialView = (): View => {
  const v = new URLSearchParams(window.location.search).get('view')
  return v === 'esperimento' || v === 'studio' ? v : 'prova'
}

export default function App() {
  const [view, setView] = useState<View>(initialView)
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between gap-6 px-6">
          <div className="flex items-center gap-3 py-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-500 text-white">
              <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-9.5Z" strokeLinejoin="round" />
                <circle cx="12" cy="14" r="3" />
              </svg>
            </div>
            <div className="leading-tight">
              <div className="text-[15px] font-bold tracking-tight text-brand-500">photo-lab</div>
              <div className="text-[11px] text-muted">La foto giusta per l’annuncio</div>
            </div>
          </div>

          <nav className="flex items-stretch gap-1 self-stretch">
            {NAV.map((n) => (
              <button
                key={n.id}
                onClick={() => setView(n.id)}
                title={n.hint}
                className={`-mb-px border-b-2 px-4 text-sm font-semibold transition-colors ${
                  view === n.id ? 'border-brand-500 text-brand-500' : 'border-transparent text-neutral-600 hover:text-ink'
                }`}
              >
                {n.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] px-6 py-8">
        {/* The product view stays mounted while the lab views are open: an upload in
            progress keeps polling and its result is still there when you come back. */}
        <div hidden={view !== 'prova'} className={view === 'prova' ? 'rise' : undefined}>
          <ProvaView />
        </div>
        {view !== 'prova' && (
          <div key={view} className="rise">
            {view === 'studio' ? <StudioView /> : <EsperimentoView />}
          </div>
        )}
      </main>
    </div>
  )
}
