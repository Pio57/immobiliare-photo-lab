import { useState } from 'react'

import { EsperimentoView } from './views/EsperimentoView'
import { ProvaView } from './views/ProvaView'
import { StudioView } from './views/StudioView'

type View = 'prova' | 'studio' | 'esperimento'

/** The product first; the two lab views sit together under one heading, so the
 *  hierarchy on screen matches the one in the case study. */
const NAV: { id: View; label: string; group: 'prodotto' | 'laboratorio' }[] = [
  { id: 'prova', label: 'Prova', group: 'prodotto' },
  { id: 'studio', label: 'Studio', group: 'laboratorio' },
  { id: 'esperimento', label: 'Esperimento', group: 'laboratorio' },
]

const initialView = (): View => {
  const v = new URLSearchParams(window.location.search).get('view')
  return v === 'esperimento' || v === 'studio' ? v : 'prova'
}

export default function App() {
  const [view, setView] = useState<View>(initialView)
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line/70 bg-[#fffdf9]/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-500 text-white shadow-[0_6px_16px_-8px_rgba(200,85,61,0.8)]">
              <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5Z" strokeLinejoin="round" />
                <circle cx="12" cy="13" r="3" />
              </svg>
            </div>
            <div>
              <h1 className="font-display text-[17px] leading-tight font-semibold">immobiliare-photo-lab</h1>
              <p className="text-xs text-muted">Quality gate sulla foto di copertina</p>
            </div>
          </div>

          <nav className="flex items-center gap-1 rounded-full border border-line bg-white/70 p-1">
            {NAV.map((n, i) => (
              <span key={n.id} className="flex items-center">
                {i > 0 && NAV[i - 1].group !== n.group && <span className="mx-1 h-4 w-px bg-line" />}
                <button
                  onClick={() => setView(n.id)}
                  className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-all ${
                    view === n.id ? 'bg-ink text-white shadow-sm' : 'text-neutral-600 hover:text-ink'
                  }`}
                >
                  {n.label}
                </button>
              </span>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-6 py-10">
        {/* The product view stays mounted while the lab views are open: an upload in
            progress keeps polling and its result is still there when you come back. */}
        <div hidden={view !== 'prova'} className={view === 'prova' ? 'rise' : undefined}>
          <ProvaView />
        </div>
        {view !== 'prova' && (
          <div key={view} className="rise">
            <p className="mb-6 text-[11px] font-semibold tracking-[0.14em] text-muted uppercase">
              Laboratorio · come il prodotto è stato misurato
            </p>
            {view === 'studio' ? <StudioView /> : <EsperimentoView />}
          </div>
        )}
      </main>
    </div>
  )
}
