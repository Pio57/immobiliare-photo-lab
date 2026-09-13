// Data contract. Mirror of cv-service/app/schemas.py — see docs/contracts.md.

/** The alternatives under test are the DIAGNOSERS: what differs between them is
 *  who names the defects and plans the parameters. The corrections are the same
 *  four modules for everyone (n8n sub-workflow "Correggi"). */
export type VariantId = 'D1' | 'D2' | 'D3'

export const VARIANT_LABEL: Record<VariantId, string> = {
  D1: 'D1 — Regole',
  D2: 'D2 — Haiku + verifica',
  D3: 'D3 — Generativo',
}

export const VARIANT_SUBTITLE: Record<VariantId, string> = {
  D1: 'regole sui numeri misurati decidono moduli e valori; nessun modello, costo 0',
  D2: 'il modello diagnostica, sceglie i valori, poi guarda il risultato e se serve corregge il piano',
  D3: 'SDXL + ControlNet ridisegna i pixel in un colpo solo; stesso gate, nessun modulo',
}

/** Defect vocabulary shared by every diagnoser and by the hand labels. */
export const DEFECT_LABEL: Record<string, string> = {
  underexposed: 'buia',
  backlit: 'controluce',
  color_cast: 'colore falsato',
  noise: 'rumorosa',
  tilt: 'storta',
  compressed: 'compressa',
  low_resolution: 'bassa risoluzione',
  blur: 'mossa / sfocata',
  perspective: 'prospettiva a imbuto',
  clutter: 'disordine',
  reshoot: 'da rifare',
  heavy_compression: 'compressione pesante',
}

export type ModuleName = 'Risoluzione' | 'Colore' | 'Luce' | 'Pulizia' | 'Raddrizza' | 'Nitidezza'

export const MODULE_INFO: Record<ModuleName, { fixes: string; params: string }> = {
  Risoluzione: { fixes: 'bassa risoluzione — ricostruzione AI, etichettata', params: 'Real-ESRGAN ×2' },
  Colore: { fixes: 'colore falsato', params: 'white_balance' },
  Luce: { fixes: 'buia / controluce', params: 'livelli, gamma, clahe_clip' },
  Pulizia: { fixes: 'rumore, blocchi JPEG', params: 'denoise' },
  Raddrizza: { fixes: 'storta', params: 'rotate_deg' },
  Nitidezza: { fixes: 'morbida dopo pulizia', params: 'sharpen' },
}

/** One correction module's record, from the Correggi sub-workflow. */
export interface Step {
  module: ModuleName
  needed: boolean
  applied: boolean
  passed: boolean | null
  retried: boolean
  fidelity: FidelityReport | null
  params: Record<string, number | string> | null
}

export interface Diagnosis {
  source: 'model' | 'heuristic'
  model: string | null
  defects: string[]
  advice: string[]
  reason: string
  recommendation: 'apply' | 'mild' | 'keep_original'
  cost_usd: number
  latency_ms: number
  error: string | null
  /** what the heuristics (D1) found on the same photo: shown when the model disagrees */
  heuristic_defects: string[]
  /** deterministic corrections to the model's plan (measured tilt used, gamma direction flipped) */
  plan_fixes: string[]
  /** D4 only: what the second look decided */
  review_verdict?: 'ok' | 'adjust' | null
}

/** One of the four versions of an upload, shown blind (V1..V4) until the agent chooses. */
export interface VersionCard {
  blind_id: string
  variant: VariantId
  label: string
  model: string | null
  source: 'model' | 'heuristic'
  status: VariantStatus
  output: string | null
  changed: boolean
  ai_reconstructed: boolean
  crop_pct: number
  fidelity: FidelityReport | null
  params: EnhanceParams | null
  steps: Step[]
  diagnosis: Diagnosis
  cost_usd: number
  latency_ms: number
  iterations: number
  error: string | null
  /** generative only: what changed, measured on the pixels after the fact */
  measured_changes?: Record<string, number> | null
}

/** Response of the n8n product webhook (Prova view): the versions in a random order. */
export interface ProductResponse {
  image_id: string
  /** the prepared original (bands trimmed, bounded size); null if not saved */
  original: string | null
  cards: VersionCard[]
  order: VariantId[]
  input_warnings: string[]
  latency_ms: number
}

/** What the Prova view sends after the agent chooses. `chosen` null = keeps the original. */
export interface Choice {
  image_id: string
  /** a variant, null = keeps the original (Prova), 'tie' = pair indistinguishable (Studio) */
  chosen: VariantId | 'tie' | null
  shown: VariantId[]
  order: VariantId[]
  /** study only: the tester's initials */
  tester?: string
}

export interface StudyInfo {
  ids: string[]
  ready: string[]
  testers: Record<string, number>
}

/** The tally served by cv-service /summary through the n8n "scelte" workflow. */
export interface SummaryRow {
  variant: VariantId
  label: string
  runs: number
  shown: number
  chosen: number
  choice_share: number | null
  choice_ci: [number, number]
  cost_mean_usd: number
  latency_p50_ms: number
  latency_p95_ms: number
  error_rate: number
  fixes_rate: number
  gate_rejected_rate: number
  unchanged_rate: number
  keep_original_rate: number
  second_look_rate: number
  ai_reconstructed_rate: number
  crop_mean_pct: number
  fidelity_min: number | null
  fidelity_mean: number | null
  diagnosis: { n_labelled: number; precision: number | null; recall: number | null; f1: number | null }
}

export interface Summary {
  generated_at: number
  runs: number
  choices: number
  keep_original_choices: number
  ties?: number
  keep_original_share: number | null
  variants: SummaryRow[]
  verdict: { n_choices: number; min_choices: number; excluded: { variant: string; why: string }[]; winner: VariantId | null; tie: VariantId[]; reason: string }
  decision_rule: string[]
}

export interface EnhanceParams {
  gamma: number
  clahe_clip: number
  white_balance: number
  denoise: number
  rotate_deg: number
  sharpen?: number
  auto_straighten: boolean
  /** whether correcting this photo is worth it at all (mild = every value halved) */
  recommendation?: 'apply' | 'mild' | 'keep_original'
}

export interface FidelityReport {
  structure: number
  structure_local_min: number
  hue_corr: number
  score: number
  threshold: number
  local_floor: number
  passed: boolean
}

export type VariantStatus = 'accepted' | 'rejected_fidelity' | 'unchanged' | 'error' | 'timeout'

export interface VariantResult {
  image_id: string
  variant: VariantId
  /** data URL; null when the model failed or timed out */
  output: string | null
  params: EnhanceParams | null
  fidelity: FidelityReport | null
  cost_usd: number
  latency_ms: number
  iterations: number
  status: VariantStatus
  error: string | null
  label?: string
  model?: string | null
  source?: 'model' | 'heuristic'
  plan?: EnhanceParams
  steps?: Step[]
  applied?: ModuleName[]
  defects?: string[]
  advice?: string[]
  /** one sentence for the estate agent, from the vision model */
  reason?: string
  recommendation?: 'apply' | 'mild' | 'keep_original'
}
