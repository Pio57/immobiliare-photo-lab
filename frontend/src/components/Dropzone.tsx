import { useRef, useState, type DragEvent } from 'react'

interface Props {
  disabled?: boolean
  onFile: (file: File) => void
}

export function Dropzone({ disabled, onFile }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  const accept = (files: FileList | null) => {
    const file = files?.[0]
    if (file && file.type.startsWith('image/')) onFile(file)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e: DragEvent) => {
        e.preventDefault()
        setOver(false)
        if (!disabled) accept(e.dataTransfer.files)
      }}
      onClick={() => !disabled && input.current?.click()}
      className={`cursor-pointer rounded-lg border-2 border-dashed bg-surface px-6 py-14 text-center transition-colors ${
        over ? 'border-brand-500 bg-brand-50' : 'border-neutral-300 hover:border-brand-500'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <input ref={input} type="file" accept="image/*" className="hidden" onChange={(e) => accept(e.target.files)} />
      <p className="text-base font-semibold">Trascina qui la foto</p>
      <p className="mt-1 text-sm text-muted">
        oppure clicca per sceglierla · JPEG o PNG, meglio l&apos;originale dalla galleria
      </p>
    </div>
  )
}
