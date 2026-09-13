import { useEffect } from 'react'
import { createPortal } from 'react-dom'

import { CompareSlider } from './CompareSlider'

interface Props {
  title: string
  subtitle?: string
  before: string
  after: string
  afterLabel: string
  onClose: () => void
}

/** Full-screen before/after: the wipe at card size hides exactly the details
 *  (grain, wall texture, halos) the comparison is about. */
export function Lightbox({ title, subtitle, before, after, afterLabel, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  // Portal: the page's <main> animates with a transform, which would otherwise
  // become the containing block of this fixed overlay and clip it.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col bg-neutral-950/95 p-4 text-white sm:p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div className="mb-3 flex items-start justify-between gap-4" onClick={(e) => e.stopPropagation()}>
        <div>
          <div className="text-base font-semibold">{title}</div>
          {subtitle && <div className="text-sm text-neutral-400">{subtitle}</div>}
        </div>
        <button
          onClick={onClose}
          className="rounded-lg border border-white/20 px-3 py-1.5 text-sm hover:bg-white/10"
          aria-label="Chiudi"
        >
          Chiudi · Esc
        </button>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center" onClick={(e) => e.stopPropagation()}>
        <div className="max-h-full w-full max-w-[min(100%,calc((100vh-120px)*4/3))]">
          <CompareSlider before={before} after={after} afterLabel={afterLabel} />
        </div>
      </div>
      <p className="mt-3 text-center text-xs text-neutral-400">
        Trascina la maniglia. Sinistra originale, destra {afterLabel}.
      </p>
    </div>,
    document.body,
  )
}
