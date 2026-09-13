import type { ReactNode } from 'react'

import type { VariantStatus } from '../types'

export function Card({ className = '', children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={`rounded-2xl border border-line bg-surface shadow-[0_1px_2px_rgba(24,24,27,0.04),0_8px_24px_-16px_rgba(24,24,27,0.18)] ${className}`}
    >
      {children}
    </div>
  )
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
      <div className="max-w-2xl">
        {eyebrow && (
          <div className="mb-1 text-[11px] font-semibold tracking-[0.14em] text-brand-500 uppercase">{eyebrow}</div>
        )}
        <h2 className="font-display text-2xl leading-tight">{title}</h2>
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
  accepted: 'Supera il gate',
  rejected_fidelity: 'Scartata dal gate',
  unchanged: 'Lasciata com’è',
  error: 'Errore del modello',
  timeout: 'Timeout',
}

export function GateBadge({ status, className = '' }: { status: VariantStatus; className?: string }) {
  return (
    <span
      className={`inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap ring-1 ring-inset ${GATE_STYLE[status]} ${className}`}
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
    <div className="border-l-2 border-line pl-3">
      <div className="text-[11px] font-medium tracking-[0.1em] text-muted uppercase">{label}</div>
      <div className="mt-1 font-display text-3xl leading-none tabular-nums">{value}</div>
      {sub && <div className="mt-1.5 text-xs leading-snug text-muted">{sub}</div>}
    </div>
  )
}

/** Horizontal share bar: the point is the comparison between rows, not the number. */
export function Bar({ value, tone = 'ink' }: { value: number; tone?: 'ink' | 'warn' }) {
  return (
    <div className="mt-1 h-1.5 w-full max-w-36 overflow-hidden rounded-full bg-neutral-200/70">
      <div
        className={`h-full rounded-full ${tone === 'warn' ? 'bg-amber-500' : 'bg-neutral-800'}`}
        style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }}
      />
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = 'primary',
  disabled,
  className = '',
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'ghost'
  disabled?: boolean
  className?: string
}) {
  const style =
    variant === 'primary'
      ? 'bg-ink text-white hover:bg-neutral-700'
      : 'border border-line bg-surface text-ink hover:border-neutral-400'
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded-xl px-4 py-2.5 text-sm font-medium transition-colors focus:ring-2 focus:ring-brand-500/40 focus:outline-none disabled:opacity-50 ${style} ${className}`}
    >
      {children}
    </button>
  )
}

export const usd = (v: number) => (v === 0 ? '≈ 0 $' : `${v.toFixed(4)} $`)
export const pct = (v: number) => `${Math.round(v * 100)}%`
export const secs = (ms: number) => `${(ms / 1000).toFixed(1)} s`
