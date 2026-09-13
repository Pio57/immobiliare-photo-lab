import { useCallback, useRef, useState } from 'react'

interface Props {
  before: string
  after: string
  beforeLabel?: string
  afterLabel?: string
}

/** Before/after wipe. The handle position is the only state; the "after" image is
 *  clipped to the right of it, so both images stay pixel-aligned while dragging. */
export function CompareSlider({ before, after, beforeLabel = 'Originale', afterLabel = 'Elaborata' }: Props) {
  const [pos, setPos] = useState(50)
  // The box takes the shape of the original photo (a phone shot is usually 3:4), so
  // the original is never cropped by the layout. The corrected photo fills the same
  // box: after a straightening crop it is slightly narrower, and letterboxing it
  // would show the original through the empty bands. The crop itself is declared
  // in the card (crop_pct), not hidden here.
  const [ratio, setRatio] = useState(4 / 3)
  const box = useRef<HTMLDivElement>(null)

  const moveTo = useCallback((clientX: number) => {
    const rect = box.current?.getBoundingClientRect()
    if (!rect) return
    setPos(Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100)))
  }, [])

  return (
    <div
      ref={box}
      style={{ aspectRatio: ratio, maxHeight: '72vh', maxWidth: `calc(72vh * ${ratio})` }}
      className="group relative mx-auto w-full cursor-ew-resize touch-none select-none overflow-hidden rounded-md bg-neutral-100"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId)
        moveTo(e.clientX)
      }}
      onPointerMove={(e) => e.currentTarget.hasPointerCapture(e.pointerId) && moveTo(e.clientX)}
    >
      <img
        src={before}
        alt={beforeLabel}
        className="absolute inset-0 h-full w-full object-cover"
        draggable={false}
        onLoad={(e) => {
          const img = e.currentTarget
          if (img.naturalWidth && img.naturalHeight) setRatio(img.naturalWidth / img.naturalHeight)
        }}
      />
      <img
        src={after}
        alt={afterLabel}
        draggable={false}
        className="absolute inset-0 h-full w-full object-cover"
        style={{ clipPath: `inset(0 0 0 ${pos}%)` }}
      />
      <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white/90 shadow" style={{ left: `${pos}%` }}>
        <div className="absolute top-1/2 left-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-[10px] font-bold text-neutral-700 shadow">
          ‹ ›
        </div>
      </div>
      <span className="pointer-events-none absolute bottom-2 left-2 rounded bg-black/55 px-1.5 py-0.5 text-[11px] text-white">
        {beforeLabel}
      </span>
      <span className="pointer-events-none absolute right-2 bottom-2 rounded bg-black/55 px-1.5 py-0.5 text-[11px] text-white">
        {afterLabel}
      </span>
    </div>
  )
}
