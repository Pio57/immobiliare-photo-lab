import type { ReactNode } from 'react'

import type { VariantStatus } from '../types'

export function Card({ className = '', children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-lg border border-line bg-surface ${className}`}>{children}</div>
}

export function SectionTitle({
  eyebrow,
  title,
  hint,
  right,
}: {
  eyebrow?: string
  title: string
  hint?: string
  right?: ReactNode
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-x-8 gap-y-2">
      <div className="max-w-3xl">
        {eyebrow && <div className="mb-1 text-xs font-semibold text-brand-500">{eyebrow}</div>}
        <h2 className="text-[22px] leading-tight font-semibold tracking-tight">{title}</h2>
        {hint && <p className="mt-1.5 text-sm leading-relaxed text-muted">{hint}</p>}
      </div>
      {right}
    </div>
  )
}

const GATE_STYLE: Record<VariantStatus, string> = {
  accepted: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  rejected_fidelity: 'bg-amber-50 text-amber-800 ring-amber-600/25',
  unchanged: 'bg-neutral-100 text-neutral-600 ring-neutral-500/20',
  error: 'bg-neutral-100 text-neutral-600 ring-neutral-500/20',
  timeout: 'bg-neutral-100 text-neutral-600 ring-neutral-500/20',
}

const GATE_LABEL: Record<VariantStatus, string> = {
  accepted: 'Supera il controllo di fedeltà',
  rejected_fidelity: 'Fermata dal controllo di fedeltà',
  unchanged: 'Lasciata com’è',
  error: 'Errore del modello',
  timeout: 'Timeout',
}

export function GateBadge({ status, className = '' }: { status: VariantStatus; className?: string }) {
  return (
    <span
      className={`inline-flex w-fit items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset ${GATE_STYLE[status]} ${className}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          status === 'accepted' ? 'bg-emerald-500' : status === 'rejected_fidelity' ? 'bg-amber-500' : 'bg-neutral-400'
        }`}
      />
      {GATE_LABEL[status]}
    </span>
  )
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="rounded-lg bg-neutral-50 px-4 py-3">
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className="mt-1 text-[26px] leading-none font-semibold tracking-tight tabular-nums">{value}</div>
      {sub && <div className="mt-1.5 text-xs leading-snug text-muted">{sub}</div>}
    </div>
  )
}

/** Horizontal share bar: the point is the comparison between rows, not the number. */
export function Bar({ value, tone = 'brand' }: { value: number; tone?: 'brand' | 'warn' | 'ok' }) {
  const fill = { brand: 'bg-brand-500', warn: 'bg-amber-500', ok: 'bg-emerald-500' }[tone]
  return (
    <div className="mt-1 h-1.5 w-full max-w-36 overflow-hidden rounded-full bg-neutral-200">
      <div className={`h-full rounded-full ${fill}`} style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }} />
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  disabled,
  className = '',
  title,
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'ghost' | 'outline'
  size?: 'md' | 'lg'
  disabled?: boolean
  className?: string
  title?: string
}) {
  const style = {
    primary: 'bg-brand-500 text-white hover:bg-brand-600',
    outline: 'border border-brand-500 bg-surface text-brand-500 hover:bg-brand-50',
    ghost: 'border border-line bg-surface text-ink hover:bg-neutral-50',
  }[variant]
  const dims = size === 'lg' ? 'px-6 py-3 text-[15px]' : 'px-4 py-2 text-sm'
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`rounded-md font-semibold transition-colors focus:ring-2 focus:ring-brand-500/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-40 ${style} ${dims} ${className}`}
    >
      {children}
    </button>
  )
}

/** Small key hint next to a button label. */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <span className="ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded border border-current/30 px-1 text-[11px] font-medium opacity-70">
      {children}
    </span>
  )
}

export const usd = (v: number) => (v === 0 ? '≈ 0 $' : `${v.toFixed(4)} $`)
export const pct = (v: number) => `${Math.round(v * 100)}%`
export const secs = (ms: number) => `${(ms / 1000).toFixed(1)} s`
