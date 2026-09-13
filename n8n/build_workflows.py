"""Generate the n8n workflow JSON files from code, so the prompts inside the
nodes come from prompts/*.md (single source of truth) and the canvases can be
rebuilt after a trial expiry with one command.

Four workflows (workflow-choice.json holds the service webhooks):
  workflow-correct.json   "Correggi" — the correction router. Four modules in sequence
                          (Colore, Luce, Pulizia, Raddrizza); each runs only if the
                          plan asks for it, is gated on its own against the original,
                          gets one conservative retry, and is skipped if it still fails.
                          Called as a sub-workflow by the other two: one implementation.
  workflow-product.json   the product (webhook): prepare -> diagnose -> plan -> Correggi -> respond.
  workflow-batch.json     the dataset run: the same three lanes on every photo of the
                          study set, one at a time -> record (what the Studio shows).

Usage (from repo root):
  cv-service\\.venv\\Scripts\\python.exe n8n\\build_workflows.py
Then in n8n import workflow-correct.json first, copy its id into .env as
N8N_CORRECT_WORKFLOW_ID, run this script again, and import the other two.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = {name: ROOT / "n8n" / f"workflow-{name}.json" for name in ("correct", "product", "batch")}

# Three families, not three flavours of the same thing:
#   D1 deterministic rules -> Correggi          (no model, ~0 $)
#   D2 Haiku diagnoses, corrects, LOOKS AGAIN   (agentic loop, ~0.01 $)
#   D3 a generative model redraws the pixels    (SDXL + ControlNet on Replicate, ~0.02 $)
# D1 and D2 go through the same Correggi; D3 is one shot, no modules, same gate.
DIAGNOSERS = {  # variant id -> (label, model or None for the heuristics, second look?)
    "D1": ("Regole", None, False),
    "D2": ("Haiku + verifica", "claude-haiku-4-5", True),
}
GENERATIVE = "D3"
GEN_VERSION = "3bb13fe1c33c35987b33792b01b71ed6529d03f165d1c2416375859f09ca9fef"  # batouresearch/sdxl-controlnet-lora
GEN_STRENGTH = 0.35  # <=0.25 changes nothing visible, >=0.35 visibly improves and starts failing the gate
GEN_PROMPT = ("the same room, real estate listing photo, well exposed, natural white balance, "
              "no noise, sharp and clean, realistic, unchanged furniture, walls and layout")
GEN_NEGATIVE = "cartoon, painting, render, blurry, extra furniture, different room, repainted walls, text, watermark"
GEN_PRICE_PER_SEC = 0.000725  # Replicate A40 (large), USD per second of predict_time
PRODUCT_MODEL = "claude-haiku-4-5"
STUDY_IDS = (ROOT / "experiments" / "study-set.txt").read_text(encoding="utf-8").split() if (ROOT / "experiments" / "study-set.txt").exists() else []
PRICE = {"claude-haiku-4-5": (1.0, 5.0)}  # USD per MTok in/out
# Super-resolution, only for inputs below 1000 px (screenshots, forwarded photos).
# Measured in experiments/flow-d.json: sharper than bicubic but further from the truth,
# thin cracks altered +-30%, invisible to the gate. So: opt-in by input size, labelled.
ESRGAN_VERSION = "b3ef194191d13140337468c916c2c5b96dd0cb06dffc032a022a31807f6a5ea8"  # nightmareai/real-esrgan
ESRGAN_SCALE = 2
ESRGAN_PRICE_PER_SEC = 0.000225  # Replicate Nvidia T4, USD/s

# The four correction modules, in pipeline order (white balance before the tone
# curve, denoise after it, rotation last). `keys` are the EnhanceParams each one owns.
MODULES = [
    ("Colore", ["white_balance"], "$json.plan.white_balance > 0"),
    ("Luce", ["gamma", "clahe_clip"], "$json.plan.gamma !== 1 || $json.plan.clahe_clip > 0"),
    ("Pulizia", ["denoise"], "$json.plan.denoise > 0"),
    ("Raddrizza", ["rotate_deg", "orientation"], "$json.plan.rotate_deg !== 0 || ($json.plan.orientation || 0) !== 0"),
    ("Nitidezza", ["sharpen"], "$json.plan.sharpen > 0"),
]
NEUTRAL = {"gamma": 1.0, "clahe_clip": 0.0, "white_balance": 0.0, "denoise": 0, "rotate_deg": 0.0, "sharpen": 0.0, "orientation": 0}


def read_env(name: str, default: str = "") -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get(name, default)


def prompt_sections(name: str) -> dict[str, str]:
    text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
    parts = re.split(r"^## (\w+).*$", text, flags=re.MULTILINE)
    return {parts[i].lower(): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def js_string(s: str) -> str:
    """A JS string literal (JSON escaping is valid JS)."""
    return json.dumps(s, ensure_ascii=False)


# ----------------------------------------------------------------- node helpers

RETRY = {"retryOnFail": True, "maxTries": 8, "waitBetweenTries": 15000}


def node(name: str, type_: str, version: float, parameters: dict, x: int, y: int, **extra) -> dict:
    return {"name": name, "type": type_, "typeVersion": version, "position": [x, y], "parameters": parameters, **extra}


def code(name: str, js: str, x: int, y: int, each_item: bool = True) -> dict:
    params = {"jsCode": js}
    if each_item:
        params["mode"] = "runOnceForEachItem"
    return node(name, "n8n-nodes-base.code", 2, params, x, y)


def http_cv(name: str, url: str, body_expr: str | None, x: int, y: int, method: str = "POST") -> dict:
    params = {"method": method, "url": url, "options": {"timeout": 180000}}
    if body_expr:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body_expr})
    return node(name, "n8n-nodes-base.httpRequest", 4.2, params, x, y, **RETRY)


def http_anthropic(name: str, x: int, y: int, batch_interval: int = 0, keep_alive: bool = False) -> dict:
    """Body is prepared by the preceding Code node in $json.body.
    `batch_interval` serialises the calls when several fire at once.
    `keep_alive` lets the product fall back to the heuristics instead of failing."""
    extra = dict(RETRY)
    if keep_alive:
        extra = {"retryOnFail": True, "maxTries": 2, "waitBetweenTries": 3000, "onError": "continueRegularOutput"}
    return node(
        name, "n8n-nodes-base.httpRequest", 4.2,
        {
            "method": "POST",
            "url": "https://api.anthropic.com/v1/messages",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "anthropicApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.body) }}",
            "options": {"timeout": 120000, **({"batching": {"batch": {"batchSize": 1, "batchInterval": batch_interval}}} if batch_interval else {})},
        },
        x, y, **extra,
    )


def if_bool(name: str, expr: str, x: int, y: int) -> dict:
    """IF on a JS boolean expression."""
    return node(name, "n8n-nodes-base.if", 2, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                       "conditions": [{"id": "c", "leftValue": f"={{{{ {expr} }}}}", "rightValue": True,
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"}, "options": {}}, x, y)


def sticky(title: str, body: str, x: int, y: int, width: int, height: int, colour: int = 7) -> dict:
    """A labelled lane on the canvas. Costs nothing at runtime and makes the
    screenshot readable: one module per lane, named, with what it demonstrates."""
    return node("sticky " + title, "n8n-nodes-base.stickyNote", 1,
                {"content": f"## {title}\n{body}", "height": height, "width": width, "color": colour}, x, y)


def execute_workflow(name: str, workflow_id: str, x: int, y: int) -> dict:
    """Call Correggi as a sub-workflow. The id comes from .env once it is imported."""
    return node(name, "n8n-nodes-base.executeWorkflow", 1.1, {
        "source": "database",
        "workflowId": {"__rl": True, "mode": "id", "value": workflow_id},
        "mode": "each",
        "options": {"waitForSubWorkflow": True},
    }, x, y)


def connect(connections: dict, src: str, dst: str, output: int = 0, index: int = 0) -> None:
    outputs = connections.setdefault(src, {"main": []})["main"]
    while len(outputs) <= output:
        outputs.append([])
    outputs[output].append({"node": dst, "type": "main", "index": index})


def chain(connections: dict, names: list[str]) -> None:
    for a, b in zip(names, names[1:]):
        connect(connections, a, b)


# ------------------------------------------------------ shared JS: diagnosis


def turn_request_js(model: str) -> str:
    """The orientation question: the four thumbnails from /prepare, one letter back."""
    return f"""
// Orientation as a four-way choice: the same photo at 0/90/180/270 deg clockwise (see /prepare).
const prep = $('Prepara').first().json;
const content = [];
(prep.turns || []).forEach((t, i) => {{ content.push({{ type: 'text', text: 'ABCD'[i] + ':' }});
  content.push({{ type: 'image', source: {{ type: 'base64', media_type: 'image/jpeg', data: t }} }}); }});
content.push({{ type: 'text', text: 'These are the same interior photo turned four ways. Exactly one is upright: floor at the bottom, ceiling at the top, walls vertical, furniture standing on the floor. Answer with the letter only.' }});
return {{ json: {{ image_id: prep.image_id, t0: Date.now(),
  body: {{ model: {js_string(model)}, max_tokens: 5, thinking: {{ type: 'disabled' }}, messages: [{{ role: 'user', content }}] }} }} }};
"""


def build_request_js(model: str, image_expr: str, stats_expr: str, turn_prefix: str | None = None) -> str:
    """Anthropic request for the AI diagnoser. `image_expr` is a JS expression for the
    image source block, `stats_expr` one for the stats object. With `turn_prefix` the
    answer of the orientation question (nodes '<prefix> richiesta' / '<prefix> modello')
    is read here and carried as `orientation`, cost and latency included."""
    d = prompt_sections("diagnosis.md")
    p_in, p_out = PRICE[model]
    turn = "" if turn_prefix is None else f"""
// The letter of the orientation question -> clockwise quarter turn (no answer = as uploaded).
const tr = $input.item.json;
const t_req = $('{turn_prefix} richiesta').first().json;
const t_text = ((tr.content || []).map(c => c.text || '').join('')).toUpperCase();
const t_letter = ['A', 'B', 'C', 'D'].find(l => t_text.includes(l));
orientation = t_letter ? [0, 90, 180, 270]['ABCD'.indexOf(t_letter)] : 0;
turn_cost = tr.usage ? tr.usage.input_tokens * {p_in} / 1e6 + tr.usage.output_tokens * {p_out} / 1e6 : 0;
turn_latency = Date.now() - t_req.t0;"""
    return f"""
// AI diagnoser request. Prompt text comes from prompts/diagnosis.md (generated, do not edit here).
const SYSTEM = {js_string(d['system'])};
const USER = {js_string(d['user'])};
const stats = {stats_expr};
const user = USER.replace('{{{{ $json.stats }}}}', JSON.stringify(stats, null, 2));
let orientation = 0, turn_cost = 0, turn_latency = 0;{turn}
return {{ json: {{ t0: Date.now(), model: {js_string(model)}, orientation, turn_cost, turn_latency,
  body: {{ model: {js_string(model)}, max_tokens: 600, thinking: {{ type: 'disabled' }}, system: SYSTEM,
    messages: [{{ role: 'user', content: [ {image_expr}, {{ type: 'text', text: user }} ] }}] }} }} }};
"""


def build_review_js(model: str, variant: str, original_expr: str, corrected_expr: str) -> str:
    """Second look: original + corrected photo, the plan and the module record.
    `original_expr` / `corrected_expr` are JS expressions for the image source blocks."""
    d = prompt_sections("diagnosis.md")
    return f"""
// Flow {variant}, second look. Prompt text comes from prompts/diagnosis.md (generated, do not edit here).
const SYSTEM = {js_string(d['system'])};
const REVIEW = {js_string(d['review'])};
const plan = $('{variant}: piano').first().json;
const image_id = plan.image_id;
const r = $input.item.json;                       // Correggi result
const text = REVIEW.replace('{{{{ plan }}}}', JSON.stringify(plan.plan, null, 1))
                   .replace('{{{{ steps }}}}', JSON.stringify(r.steps.filter(s => s.needed).map(({{ module, applied, params }}) => ({{ module, applied, params }})), null, 1));
return {{ json: {{ t0: Date.now(), model: {js_string(model)}, correggi: r,
  body: {{ model: {js_string(model)}, max_tokens: 600, thinking: {{ type: 'disabled' }}, system: SYSTEM,
    messages: [{{ role: 'user', content: [
      {{ type: 'text', text: 'ORIGINAL:' }}, {original_expr},
      {{ type: 'text', text: 'CORRECTED:' }}, {corrected_expr},
      {{ type: 'text', text }} ] }}] }} }} }};
"""


def parse_js(model: str, request_node: str) -> str:
    p_in, p_out = PRICE[model]
    return f"""
// Parse the diagnoser's JSON; cost from usage at list price. A malformed or missing
// answer does not stop anything: it is recorded as an error and the plan falls back
// to the heuristic diagnosis (D1), which /prepare already computed.
const r = $input.item.json;
const req = $('{request_node}').first().json;
const t0 = req.t0;
const text = (r.content || []).map(c => c.text || '').join('');
const cost_usd = (r.usage ? r.usage.input_tokens * {p_in} / 1e6 + r.usage.output_tokens * {p_out} / 1e6 : 0) + (req.turn_cost || 0);
let plan = null, defects = [], advice = [], reason = '', recommendation = 'apply', error = null, verdict = 'ok';
if (!r.content) error = 'diagnosis failed: ' + (r.error && r.error.message ? r.error.message : (r.message || 'no response')).slice(0, 120);
else try {{
  const start = text.indexOf('{{'), end = text.lastIndexOf('}}');
  const o = JSON.parse(text.slice(start, end + 1));
  defects = Array.isArray(o.defects) ? o.defects : [];
  advice = Array.isArray(o.advice) ? o.advice : [];
  reason = o.reason || '';
  recommendation = ['apply', 'mild', 'keep_original'].includes(o.recommendation) ? o.recommendation : 'apply';
  verdict = o.verdict === 'adjust' ? 'adjust' : 'ok';
  // The model speaks in stops (+1 = brighter), the pipeline in gamma (< 1 = brighter):
  // gamma = 2^(-exposure/2), so +1 -> 0.71, +2 -> 0.5, -1 -> 1.41. Models invert gamma
  // routinely; nobody inverts "brighter".
  const exposure = Math.max(-2, Math.min(2, Number(o.exposure ?? 0)));
  plan = {{ gamma: Number(Math.pow(2, -exposure / 2).toFixed(2)), clahe_clip: Number(o.clahe_clip ?? 0), white_balance: Number(o.white_balance ?? 0),
           denoise: Math.round(Number(o.denoise ?? 0)), rotate_deg: Number(o.rotate_deg ?? 0),
           sharpen: Number(o.sharpen ?? 0), orientation: req.orientation || 0, exposure }};
  if (Object.values(plan).some(v => Number.isNaN(v))) throw new Error('non-numeric parameter');
}} catch (e) {{ error = `diagnosis JSON unreadable: ${{String(e).slice(0, 80)}} | ${{text.slice(0, 120)}}`; }}
return {{ json: {{ model: {js_string(model)}, plan, defects, advice, reason, recommendation, verdict, cost_usd, latency_ms: Date.now() - t0 + (req.turn_latency || 0), error, body: null }} }};
"""


def plan_js(variant: str, label: str, prepare_node: str, diagnosis_node: str | None, input_expr: str, save_as_expr: str) -> str:
    """Turn a diagnosis (model or heuristic) into the item Correggi expects."""
    return f"""
// The plan for Correggi: which parameters, from whom, and where the result goes.
const prep = $('{prepare_node}').first().json;
let first_turn = 0;
try {{ first_turn = $('{variant}: richiesta').first().json.orientation || 0; }} catch (e) {{}}
const heuristic = {{ plan: prep.heuristic_params, defects: prep.heuristic_defects, advice: [], reason: '',
  recommendation: prep.heuristic_params.recommendation || 'apply', cost_usd: 0, latency_ms: 0, error: null, model: null }};
let d = heuristic, source = 'heuristic';
{"" if diagnosis_node is None else f"const m = $('{diagnosis_node}').first().json; if (m.plan) {{ d = m; source = 'model'; }} else {{ d = {{ ...heuristic, error: m.error, model: m.model, cost_usd: m.cost_usd, latency_ms: m.latency_ms }}; }}"}
const plan = {{ ...d.plan }};
if (source === 'model' && !plan.orientation && first_turn) plan.orientation = first_turn;  // the second look has no letter of its own
// Geometry: when the line detector measured a tilt, its value wins (sign and size
// come from actual edges). The model's rotate_deg counts only where the detector
// found nothing to measure. A vision model reads "leans left" right, the sign of
// the angle less so; and the gate cannot catch a wrong sign (it aligns the original).
const measured = Number(prep.stats.tilt_deg || 0);
const fixes = [];
const defects = [...(d.defects || [])], advice = [...(d.advice || [])];
// The quarter turn is the model's pick among the four thumbnails (see /prepare `turns`);
// a turned photo is `rotated` whatever the model wrote in the list.
if (plan.orientation && !defects.includes('rotated')) defects.push('rotated');
if (!plan.orientation) {{ const i = defects.indexOf('rotated'); if (i >= 0) defects.splice(i, 1); }}
if (Math.abs(measured) > 15) {{
  // Rolled beyond the rotation limit: no half correction, the agent is told to reshoot.
  if (plan.rotate_deg !== 0) fixes.push(`rotate_deg ${{plan.rotate_deg}} -> 0 (tilt ${{measured}} beyond range)`);
  plan.rotate_deg = 0;
  if (!defects.includes('tilt')) defects.push('tilt');
  if (!advice.includes('reshoot')) advice.push('reshoot');
}} else if (measured !== 0 && plan.rotate_deg !== measured) {{ plan.rotate_deg = measured; fixes.push('rotate_deg: measured value used'); }}
// A plan that darkens a dark photo (or brightens a bright one) is a sign error, not
// a judgement: flip it and say so in the record, so the batch can count how often.
const luma = Number(prep.stats.mean_luminance || 128);
if ((luma < 100 && plan.gamma > 1) || (luma > 190 && plan.gamma < 1)) {{ plan.gamma = Number((1 / plan.gamma).toFixed(2)); fixes.push('gamma: direction flipped'); }}
// Compressed input: local contrast amplifies the JPEG blotches on flat walls and a
// strong unsharp mask redraws the block edges. Measured, so enforced, not suggested.
const compressed = (prep.stats.input_warnings || []).some(w => String(w).startsWith('heavy_compression') || String(w).startsWith('low_resolution'));
if (compressed && plan.clahe_clip > 0) {{ fixes.push(`clahe_clip ${{plan.clahe_clip}} -> 0 (compressed input)`); plan.clahe_clip = 0; }}
if (compressed && plan.sharpen > 0.2) {{ fixes.push(`sharpen ${{plan.sharpen}} -> 0.2 (compressed input)`); plan.sharpen = 0.2; }}
delete plan.exposure;
if (d.recommendation === 'keep_original') {{ const o = plan.orientation || 0; Object.assign(plan, {json.dumps(NEUTRAL)}); if (o) {{ plan.orientation = o; d.recommendation = 'apply'; fixes.push('keep_original -> apply: the photo had to be turned'); }} }}
plan.recommendation = d.recommendation === 'mild' ? 'mild' : 'apply';
return {{ json: {{ variant: {js_string(variant)}, label: {js_string(label)}, image_id: prep.image_id, source, model: d.model || null, verdict: d.verdict || null,
  input: {{ ...{input_expr}, low_resolution: (prep.stats.input_warnings || []).some(w => String(w).startsWith('low_resolution')) }}, save_as: {save_as_expr},
  plan, plan_fixes: fixes, defects, advice, reason: d.reason, recommendation: d.recommendation,
  diagnosis_cost_usd: d.cost_usd, diagnosis_latency_ms: d.latency_ms, diagnosis_error: d.error, t0: Date.now() }} }};
"""


# ------------------------------------------------------------ Correggi (sub)


def build_correct() -> dict:
    cv_url = read_env("CV_SERVICE_PUBLIC_URL", "https://CHANGE-ME.ngrok-free.app")

    init_js = f"""
// State that travels through the four modules. `accepted` grows with every module
// that passes its gate; `steps` records what happened to each one.
const j = $input.item.json;
const plan = {{ ...{json.dumps(NEUTRAL)}, ...(j.plan || {{}}) }};
const modules = {json.dumps([m[0] for m in MODULES])};
return {{ json: {{ input: j.input, save_as: j.save_as || null, plan, ai_reconstructed: false,
  accepted: {{ recommendation: plan.recommendation || 'apply' }},
  steps: [{{ module: 'Risoluzione', needed: false, applied: false, passed: null, retried: false, fidelity: null, params: null }},
          ...modules.map(m => ({{ module: m, needed: false, applied: false, passed: null, retried: false, fidelity: null, params: null }}))],
  retry: {{}} }} }};
"""

    def apply_body(keys: list[str]) -> str:
        cand = ", ".join(f"{k}: $json.plan.{k}" for k in keys)
        return ("={{ JSON.stringify({ image_b64: $json.input.image_b64, image_id: $json.input.image_id, return_image: false, "
                f"params: Object.assign({{}}, $json.accepted, {{ {cand} }}) }}) }}}}")

    def state_js(module: str) -> str:
        """The state that fed `applica`: on the first pass it comes from `serve?`, on the
        retry from `riprova?` (whose plan carries the conservative values)."""
        return f"""
let s = null;
try {{ const again = $('{module}: riprova?').first().json; if (again._again) s = again; }} catch (e) {{}}
if (!s) s = $('{module}: serve?').first().json;
s = JSON.parse(JSON.stringify(s));"""

    def ok_js(module: str, keys: list[str]) -> str:
        return f"""
// {module} passed its gate: its PLANNED parameters join the accepted set (the
// resolved ones may be halved by `mild`; storing them would halve twice downstream).
{state_js(module)}
const r = $input.item.json;
const step = s.steps.find(x => x.module === {js_string(module)});
Object.assign(step, {{ needed: true, applied: true, passed: true, fidelity: r.fidelity, params: {{ {", ".join(f"{k}: r.params.{k}" for k in keys)}{", crop_pct: r.crop_pct" if "rotate_deg" in keys else ""} }} }});
for (const k of {json.dumps(keys)}) s.accepted[k] = s.plan[k];
s._again = false;
return {{ json: s }};
"""

    def fail_js(module: str, keys: list[str]) -> str:
        return f"""
// {module} failed its gate. First time: retry once with the conservative values
// cv-service suggests (the self-check loop). Second time: skip the module, keep
// what was accepted so far. The photo is never left worse than the previous step.
{state_js(module)}
const r = $input.item.json;
const step = s.steps.find(x => x.module === {js_string(module)});
const key = {js_string(module)};
if (!s.retry[key] && r.suggested_conservative_params) {{
  s.retry[key] = true;
  for (const k of {json.dumps(keys)}) s.plan[k] = r.suggested_conservative_params[k];
  Object.assign(step, {{ needed: true, retried: true }});
  s._again = true;
}} else {{
  Object.assign(step, {{ needed: true, applied: false, passed: false, fidelity: r.fidelity, params: {{ {", ".join(f"{k}: r.params.{k}" for k in keys)} }} }});
  s._again = false;
}}
return {{ json: s }};
"""

    final_body = ("={{ JSON.stringify({ image_b64: $json.input.image_b64, image_id: $json.input.image_id, save_as: $json.save_as, "
                  "return_image: true, params: $json.accepted }) }}")
    result_js = """
// What Correggi returns to the caller: the corrected photo (or the untouched original
// when nothing was applied), the accepted parameters, the per-module record.
const s = $('Finale: stato').first().json;
const r = $input.item.json;
const applied = s.steps.filter(x => x.applied).map(x => x.module);
return { json: { output_b64: r.image_b64 || null, output_path: r.output_path || null, params: r.params, fidelity: r.fidelity, crop_pct: r.crop_pct || 0,
  steps: s.steps.map(({ module, needed, applied, passed, retried, fidelity, params }) => ({ module, needed, applied, passed, retried, fidelity, params })),
  applied, changed: applied.length > 0, ai_reconstructed: s.ai_reconstructed === true } };
"""

    esrgan_request_js = f"""
// Real-ESRGAN x{ESRGAN_SCALE}: image inline (small by definition: this lane runs only below 1000 px)
// or by dataset URL in the batch.
const s = $input.item.json;
const image = s.input.image_id ? `${{{js_string(cv_url)}}}/dataset/${{s.input.image_id}}/file` : `data:image/jpeg;base64,${{s.input.image_b64}}`;
return {{ json: {{ ...s, _t0: Date.now(), body: {{ version: {js_string(ESRGAN_VERSION)}, input: {{ image, scale: {ESRGAN_SCALE}, face_enhance: false }} }} }} }};
"""
    esrgan_ok_js = f"""
// The upscaled photo becomes the working image for every module after this one.
// Its 'fidelity' against the input is informational: super-resolution invents
// texture below the scale the gate measures, so the gate cannot object. What
// protects the reader is the label (ai_reconstructed), not the number.
const s = JSON.parse(JSON.stringify($('Risoluzione: richiesta').first().json));
const pred = $('Risoluzione: Real-ESRGAN').first().json;
const r = $input.item.json;
delete s.body;
s.input = {{ ...s.input, image_b64: r.image_b64, image_id: undefined }};
s.ai_reconstructed = true;
// The plan was made for the small, blocky input. The upscaled photo is already
// smooth and block-free: denoising it again turns fabric into wax, and a strong
// unsharp mask redraws it in patches (measured: local-minimum fidelity 0.85 -> 0.92).
const adjusted = [];
if (s.plan.denoise > 0) {{ adjusted.push(`denoise ${{s.plan.denoise}} -> 0`); s.plan.denoise = 0; }}
if (s.plan.clahe_clip > 1) {{ adjusted.push(`clahe_clip ${{s.plan.clahe_clip}} -> 1`); s.plan.clahe_clip = 1; }}
if (s.plan.sharpen > 0.2) {{ adjusted.push(`sharpen ${{s.plan.sharpen}} -> 0.2`); s.plan.sharpen = 0.2; }}
const cost = Number((((pred.metrics && pred.metrics.predict_time) || 0) * {ESRGAN_PRICE_PER_SEC}).toFixed(5));
Object.assign(s.steps[0], {{ needed: true, applied: true, passed: true, fidelity: r.fidelity,
  params: {{ scale: {ESRGAN_SCALE}, cost_usd: cost, latency_ms: Date.now() - s._t0, plan_adjusted: adjusted.join(', ') || undefined }} }});
delete s._t0;
return {{ json: s }};
"""
    esrgan_skip_js = """
// Replicate failed or timed out: go on with the photo as it is, and say so.
const s = JSON.parse(JSON.stringify($('Risoluzione: richiesta').first().json));
delete s.body; delete s._t0;
Object.assign(s.steps[0], { needed: true, applied: false, passed: false, params: { error: String(($input.item.json.error || $input.item.json.status || 'failed')).slice(0, 120) } });
return { json: s };
"""
    nodes = [
        sticky("Correggi - il router delle correzioni",
               "Un modulo per difetto, in sequenza. Ogni modulo parte SOLO se il piano lo chiede, applica il suo parametro sopra quelli gia' accettati, "
               "ripartendo sempre dall'originale, e passa dal gate di fedelta'. Bocciato: un tentativo con i valori conservativi suggeriti da cv-service, "
               "poi il modulo viene saltato. Foto solo storta = passa solo da Raddrizza. Chiamato dal prodotto e dall'esperimento: una sola implementazione.",
               -140, -260, 5400, 220, 4),
        node("Da chi chiama", "n8n-nodes-base.executeWorkflowTrigger", 1.1, {"inputSource": "passthrough"}, -40, 60),
        code("Stato iniziale", init_js, 180, 60),
    ]
    connections: dict = {}
    connect(connections, "Da chi chiama", "Stato iniziale")
    # ---- Risoluzione: the one generative module, opt-in by input size, labelled
    nodes += [
        sticky("Risoluzione", "Solo sotto 1000 px (screenshot, inoltri). Real-ESRGAN x2 su Replicate: inventa texture, il gate non puo' vederlo. L'output porta ai_reconstructed=true e l'agente lo legge.",
               400, -40, 1180, 560, 7),
        if_bool("Risoluzione: serve?", "$json.input.low_resolution === true", 460, 60),
        code("Risoluzione: richiesta", esrgan_request_js, 660, 160),
        node("Risoluzione: Real-ESRGAN", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": "https://api.replicate.com/v1/predictions",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Prefer", "value": "wait=60"}]},
            "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.body) }}",
            "options": {"timeout": 120000},
        }, 860, 160, retryOnFail=True, maxTries=2, waitBetweenTries=5000, onError="continueRegularOutput"),
        if_bool("Risoluzione: succeeded?", "$json.status === 'succeeded'", 1060, 160),
        http_cv("Risoluzione: ricevi", f"{cv_url}/gate_remote",
                "={{ JSON.stringify({ original_b64: $('Risoluzione: richiesta').first().json.input.image_b64, image_id: $('Risoluzione: richiesta').first().json.input.image_id, candidate_url: Array.isArray($json.output) ? $json.output[0] : $json.output }) }}",
                1260, 160),
        code("Risoluzione: ok", esrgan_ok_js, 1460, 60),
        code("Risoluzione: saltata", esrgan_skip_js, 1260, 340),
    ]
    connect(connections, "Stato iniziale", "Risoluzione: serve?")
    connect(connections, "Risoluzione: serve?", "Risoluzione: richiesta", output=0)
    chain(connections, ["Risoluzione: richiesta", "Risoluzione: Real-ESRGAN", "Risoluzione: succeeded?"])
    connect(connections, "Risoluzione: succeeded?", "Risoluzione: ricevi", output=0)
    connect(connections, "Risoluzione: succeeded?", "Risoluzione: saltata", output=1)
    connect(connections, "Risoluzione: ricevi", "Risoluzione: ok")
    prev_outputs: list[tuple[str, int]] = [("Risoluzione: serve?", 1), ("Risoluzione: ok", 0), ("Risoluzione: saltata", 0)]
    colours = [5, 3, 6, 2, 4]
    for i, (module, keys, needed_expr) in enumerate(MODULES):
        x = 1660 + i * 620
        nodes += [
            sticky(module, {"Colore": "white_balance", "Luce": "livelli + gamma + clahe_clip", "Pulizia": "denoise", "Raddrizza": "rotate_deg", "Nitidezza": "sharpen (unsharp mask)"}[module],
                   x - 60, -40, 600, 560, colours[i]),
            if_bool(f"{module}: serve?", needed_expr, x, 60),
            http_cv(f"{module}: applica", f"{cv_url}/apply", apply_body(keys), x + 200, 160),
            if_bool(f"{module}: gate", "$json.fidelity.passed", x + 400, 160),
            code(f"{module}: ok", ok_js(module, keys), x + 400, 20),
            code(f"{module}: bocciata", fail_js(module, keys), x + 200, 340),
            if_bool(f"{module}: riprova?", "$json._again", x + 400, 340),
        ]
        for src, out in prev_outputs:
            connect(connections, src, f"{module}: serve?", output=out)
        connect(connections, f"{module}: serve?", f"{module}: applica", output=0)
        connect(connections, f"{module}: applica", f"{module}: gate")
        connect(connections, f"{module}: gate", f"{module}: ok", output=0)
        connect(connections, f"{module}: gate", f"{module}: bocciata", output=1)
        connect(connections, f"{module}: bocciata", f"{module}: riprova?")
        connect(connections, f"{module}: riprova?", f"{module}: applica", output=0)  # the visible loop
        prev_outputs = [(f"{module}: serve?", 1), (f"{module}: ok", 0), (f"{module}: riprova?", 1)]
    x = 1660 + len(MODULES) * 620
    nodes += [
        sticky("Finale", "Una sola applicazione dei parametri accettati, dall'originale: e' l'immagine restituita e il suo gate e' quello cumulativo.", x - 60, -40, 620, 560, 7),
        code("Finale: stato", "return { json: $input.item.json };", x, 60),
        http_cv("Finale: applica", f"{cv_url}/apply", final_body, x + 200, 60),
        code("Risultato", result_js, x + 400, 60),
    ]
    for src, out in prev_outputs:
        connect(connections, src, "Finale: stato", output=out)
    chain(connections, ["Finale: stato", "Finale: applica", "Risultato"])
    return {"name": "photo-lab Correggi (router)", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}


# ------------------------------------------------- one diagnoser, one lane


def record_js(variant: str, second_look: bool, chained_to: str | None) -> str:
    """VariantResult for one diagnoser (see docs/contracts.md). `chained_to` names the
    previous Record node whose variants this one appends to (batch: sequential lanes);
    None makes an independent record (product: parallel lanes, merged later)."""
    prev = "[]" if chained_to is None else f"$('{chained_to}').first().json.variants"
    second = ""
    if second_look:
        second = f"""
// In a loop, a node that did not run this time still answers .first() with its
// previous item: the image_id check keeps a stale second round out of this record.
try {{ const p2 = $('{variant}: piano 2').first().json; if (p2 && p2.plan && p2.image_id === plan.image_id) {{ rounds.push(p2);
  plan = {{ ...p2, plan_fixes: [...(plan.plan_fixes || []), ...(p2.plan_fixes || [])],
    diagnosis_cost_usd: rounds.reduce((a, x) => a + (x.diagnosis_cost_usd || 0), 0),
    diagnosis_latency_ms: rounds.reduce((a, x) => a + (x.diagnosis_latency_ms || 0), 0), t0: rounds[0].t0 }}; }} }} catch (e) {{}}"""
    return f"""
// VariantResult for {variant}: diagnosis + correction record, see docs/contracts.md.
let plan = $('{variant}: piano').first().json;
let rounds = [plan];{second}
const r = $input.item.json;
const image_id = plan.image_id;
const status = plan.diagnosis_error && plan.source === 'heuristic' && {js_string(variant)} !== 'D1' ? 'error'
  : (r.changed ? (r.fidelity.passed ? 'accepted' : 'rejected_fidelity') : 'unchanged');
const v = {{ image_id, variant: {js_string(variant)}, label: plan.label, model: plan.model, source: plan.source,
  output_path: r.output_path, output_b64: r.output_b64 || null, params: r.params, plan: plan.plan, fidelity: r.fidelity, steps: r.steps,
  applied: r.applied, ai_reconstructed: r.ai_reconstructed === true, crop_pct: r.crop_pct || 0,
  defects: plan.defects, advice: plan.advice, reason: plan.reason, recommendation: plan.recommendation, plan_fixes: plan.plan_fixes,
  cost_usd: Number((plan.diagnosis_cost_usd || 0).toFixed(5)), latency_ms: Date.now() - plan.t0 + (plan.diagnosis_latency_ms || 0),
  iterations: rounds.length, review_verdict: rounds.length > 1 ? 'adjust' : (plan.verdict || null), status, error: plan.diagnosis_error || null }};
return {{ json: {{ image_id, variants: [...{prev}, v], judge: [] }} }};
"""


def diagnoser_lane(nodes: list, connections: dict, *, variant: str, label: str, model: str | None, second_look: bool,
                   src: str, x: int, y: int, correct_id: str, image_expr: str, input_expr: str, save_as_expr: str,
                   original_expr: str, corrected_expr: str, chained_to: str | None) -> str:
    """Diagnosis -> plan -> Correggi -> (second look -> Correggi again) -> Record.
    Returns the name of the Record node. Same lane in the product and in the batch:
    what differs is only where the image comes from (upload vs dataset)."""
    stats_expr = "$('Prepara').first().json.stats"
    if model is None:
        nodes.append(code(f"{variant}: piano", plan_js(variant, label, "Prepara", None, input_expr, save_as_expr), x, y))
        connect(connections, src, f"{variant}: piano")
    else:
        # Orientation first, as its own question: the photo turned four ways, "which one is
        # upright?". Asked alone the model never misses (22/22 on the bench); folded into the
        # diagnosis prompt it misses one strongly tilted photo out of three.
        nodes += [
            code(f"{variant}: verso richiesta", turn_request_js(model), x - 440, y + 160),
            http_anthropic(f"{variant}: verso modello", x - 220, y + 160, keep_alive=True),
            code(f"{variant}: richiesta", build_request_js(model, image_expr, stats_expr, f"{variant}: verso"), x, y),
            http_anthropic(f"{variant}: modello", x + 220, y, keep_alive=True),
            code(f"{variant}: lettura", parse_js(model, f"{variant}: richiesta"), x + 440, y),
            code(f"{variant}: piano", plan_js(variant, label, "Prepara", f"{variant}: lettura", input_expr, save_as_expr), x + 660, y),
        ]
        connect(connections, src, f"{variant}: verso richiesta")
        chain(connections, [f"{variant}: verso richiesta", f"{variant}: verso modello", f"{variant}: richiesta", f"{variant}: modello", f"{variant}: lettura", f"{variant}: piano"])
    nodes.append(execute_workflow(f"{variant}: Correggi", correct_id, x + 900, y))
    connect(connections, f"{variant}: piano", f"{variant}: Correggi")
    record = f"Record {variant}"
    if second_look:
        nodes += [
            code(f"{variant}: verifica richiesta", build_review_js(model, variant, original_expr, corrected_expr), x + 1120, y),
            http_anthropic(f"{variant}: verifica modello", x + 1340, y, keep_alive=True),
            code(f"{variant}: verifica lettura", parse_js(model, f"{variant}: verifica richiesta"), x + 1560, y),
            if_bool(f"{variant}: secondo giro?", "$json.verdict === 'adjust' && $json.plan !== null", x + 1780, y),
            code(f"{variant}: piano 2", plan_js(variant, label, "Prepara", f"{variant}: verifica lettura", input_expr, save_as_expr), x + 2000, y - 80),
            execute_workflow(f"{variant}: Correggi 2", correct_id, x + 2220, y - 80),
            code(f"{variant}: tieni il primo", f"return {{ json: $('{variant}: verifica richiesta').first().json.correggi }};", x + 2000, y + 100),
            code(record, record_js(variant, True, chained_to), x + 2440, y),
        ]
        chain(connections, [f"{variant}: Correggi", f"{variant}: verifica richiesta", f"{variant}: verifica modello",
                            f"{variant}: verifica lettura", f"{variant}: secondo giro?"])
        connect(connections, f"{variant}: secondo giro?", f"{variant}: piano 2", output=0)
        chain(connections, [f"{variant}: piano 2", f"{variant}: Correggi 2", record])
        connect(connections, f"{variant}: secondo giro?", f"{variant}: tieni il primo", output=1)
        connect(connections, f"{variant}: tieni il primo", record)
    else:
        nodes.append(code(record, record_js(variant, False, chained_to), x + 1120, y))
        connect(connections, f"{variant}: Correggi", record)
    return record


LANE_NOTES = {
    "D1": ("D1 - Regole", "Regole sui numeri misurati da /prepare decidono cosa correggere e con quali valori. Zero modelli, costo 0. La baseline: se un modello non la batte, non serve.", 5),
    "D2": ("D2 - Haiku + verifica", "Prima il verso, come domanda a parte: la foto girata in quattro modi, 'qual e' quella dritta?' (a scelta non sbaglia, a gradi si'). Poi il modello guarda foto + numeri, nomina i difetti (vocabolario fisso), sceglie i VALORI dei moduli che servono. Poi guarda il RISULTATO accanto all'originale: se vede ancora un difetto (o uno nuovo: velo, chiazze, cera) corregge il piano e rifa' un giro. Il flusso agentico chiuso.", 3),
    "D3": ("D3 - Generativo", "SDXL + ControlNet (Replicate) riceve la foto e l'istruzione 'ben esposta, colori naturali, pulita, nitida, stanza invariata' e RIDISEGNA i pixel. Un colpo solo, niente moduli, non puo' raddrizzare. Stesso gate: e' l'unico che puo' violare la policy, quindi l'unico che il gate boccia davvero.", 6),
}


def generative_lane(nodes: list, connections: dict, *, src: str, x: int, y: int, cv_url: str,
                    image_expr: str, original_ref_expr: str, save_as_expr: str, chained_to: str | None) -> str:
    """D3: one Replicate call, then cv-service fetches the output and gates it.
    `image_expr` is the JS for the model's input image (data URI or dataset URL),
    `original_ref_expr` the JSON fields that name the original for /gate_remote."""
    v = GENERATIVE
    request_js = f"""
// {v}: constrained img2img (SDXL + ControlNet canny). The prompt asks for the same
// corrections the modules make, in words; the model decides the pixels.
// The hosted model has a safety checker with no switch, and it misfires on beds and
// clothes ("NSFW content detected"): the seed moves on each retry (see 'nsfw?').
const prep = $('Prepara').first().json;
let attempt = 0;
try {{ const r = $('{v}: nuovo seed').first().json; if (r && r.image_id === prep.image_id) attempt = r._attempt || 0; }} catch (e) {{}}
return {{ json: {{ image_id: prep.image_id, t0: Date.now(), _attempt: attempt, body: {{ version: {js_string(GEN_VERSION)}, input: {{
  image: {image_expr}, prompt: {js_string(GEN_PROMPT)}, negative_prompt: {js_string(GEN_NEGATIVE)},
  img2img: true, strength: {GEN_STRENGTH}, condition_scale: 1.1, guidance_scale: 5, num_inference_steps: 30,
  refine: 'no_refiner', apply_watermark: false, seed: 42 + attempt * 1000 }} }} }} }};
"""
    record_js_gen = f"""
// VariantResult for {v}: no diagnosis, no modules — one pseudo-step so the tally can
// count gate rejections the same way for every family.
const req = $('{v}: richiesta').first().json;
let pred = $('{v}: Replicate').first().json;
try {{ const last = $('{v}: conta').first().json; if (last && last.id === pred.id) pred = last; }} catch (e) {{}}
const image_id = req.image_id;
const predict_time = (pred.metrics && pred.metrics.predict_time) || 0;
const cost_usd = Number((predict_time * {GEN_PRICE_PER_SEC}).toFixed(5));
const latency_ms = Date.now() - req.t0;
let g = null;
try {{ g = $('{v}: gate').first().json; if (g && g.image_id && g.image_id !== image_id) g = null; }} catch (e) {{}}
// The gate ran only on a succeeded prediction: its answer for this image is the proof,
// whatever run of 'Replicate' .first() happens to return after a retry.
const ok = Boolean(g && g.fidelity);
const status = !ok ? (pred.status === 'processing' ? 'timeout' : 'error') : (g.fidelity.passed ? 'accepted' : 'rejected_fidelity');
const v = {{ image_id, variant: {js_string(v)}, label: 'Generativo', model: 'sdxl-controlnet', source: 'model',
  output_path: ok ? `dataset/processed/${{image_id}}_{v}.jpg` : null, output_b64: ok ? g.image_b64 : null,
  params: {{ strength: {GEN_STRENGTH} }}, plan: null, fidelity: ok ? g.fidelity : null,
  // What it did, read off the pixels (a black box reports no decisions): one row per
  // module, 'applied' when the measured change is beyond what re-encoding alone causes.
  steps: (() => {{
    const m = (ok && g.measured_changes) || {{}};
    const passed = ok ? g.fidelity.passed : null;
    const row = (module, needed, params) => ({{ module, needed, applied: needed && Boolean(passed), passed: needed ? passed : null, retried: false, fidelity: needed && ok ? g.fidelity : null, params: needed ? params : null }});
    return [
      row('Risoluzione', (m.scale || 1) >= 1.5, {{ scale: m.scale }}),
      row('Colore', m.cast_before !== undefined && Math.abs(m.cast_after - m.cast_before) >= 1.5, {{ cast: `${{m.cast_before}} -> ${{m.cast_after}}` }}),
      row('Luce', Math.abs(m.luminance_delta || 0) >= 5, {{ luminanza: (m.luminance_delta > 0 ? '+' : '') + m.luminance_delta, contrasto: (m.contrast_delta > 0 ? '+' : '') + m.contrast_delta }}),
      row('Pulizia', m.noise_before !== undefined && m.noise_after < m.noise_before * 0.8, {{ rumore: `${{m.noise_before}} -> ${{m.noise_after}}` }}),
      row('Raddrizza', Math.abs((m.tilt_after || 0) - (m.tilt_before || 0)) >= 1, {{ tilt: `${{m.tilt_before}} -> ${{m.tilt_after}}` }}),
      row('Nitidezza', m.sharpness_ratio !== undefined && Math.abs(m.sharpness_ratio - 1) >= 0.2, {{ nitidezza: `x${{m.sharpness_ratio}}` }}),
    ];
  }})(),
  measured_changes: ok ? g.measured_changes : null,
  applied: ok && g.fidelity.passed ? ['Generativo'] : [], ai_reconstructed: true, crop_pct: 0,
  defects: [], advice: [], reason: 'Ridisegno generativo: nessuna diagnosi, il modello decide da solo cosa cambiare.', recommendation: 'apply', plan_fixes: [],
  cost_usd, latency_ms, iterations: 1, review_verdict: null, status, error: ok ? null : (pred.error || pred.status || 'failed') }};
const prev = {"[]" if chained_to is None else f"$('{chained_to}').first().json.variants"};
return {{ json: {{ image_id, variants: [...prev, v], judge: [] }} }};
"""
    nodes += [
        code(f"{v}: richiesta", request_js, x, y),
        node(f"{v}: Replicate", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": "https://api.replicate.com/v1/predictions",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Prefer", "value": "wait=60"}]},
            "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.body) }}",
            "options": {"timeout": 120000},
        }, x + 220, y, retryOnFail=True, maxTries=2, waitBetweenTries=5000, onError="continueRegularOutput"),
        if_bool(f"{v}: succeeded?", "$json.status === 'succeeded'", x + 440, y),
        # Cold start: `Prefer: wait=60` comes back with the prediction still 'starting'.
        # Poll it every 15 s, at most 12 times (3 min), before calling it a timeout.
        if_bool(f"{v}: in corso?", "($json.status === 'starting' || $json.status === 'processing') && ($json._polls || 0) < 12", x + 440, y + 180),
        node(f"{v}: attendi", "n8n-nodes-base.wait", 1.1, {"amount": 15, "unit": "seconds"}, x + 220, y + 180),
        node(f"{v}: stato", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "GET", "url": "={{ $json.urls.get }}",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth", "options": {"timeout": 30000},
        }, x + 220, y + 320, retryOnFail=True, maxTries=2, waitBetweenTries=5000, onError="continueRegularOutput"),
        code(f"{v}: conta", f"""
// Poll counter: this node's previous output in the same execution carries the count.
let n = 0; try {{ n = $('{v}: conta').first().json._polls || 0; }} catch (e) {{}}
return {{ json: {{ ...$input.item.json, _polls: n + 1 }} }};
""", x + 440, y + 320),
        # The safety checker of the hosted model misfires on bedrooms (beds, clothes on the
        # bed): a failed prediction that says NSFW is retried up to twice with another seed.
        # A 429 (two uploads at once) takes the same road, after a pause.
        if_bool(f"{v}: nsfw?", f"/NSFW|429|spacing/.test(String(($json.error && ($json.error.message || $json.error)) || '')) && (($('{v}: richiesta').first().json._attempt || 0) < 2)", x + 660, y + 180),
        code(f"{v}: nuovo seed", f"""
// Another seed for the same request; the counter travels through this node. A rate
// limit gets a pause first.
const req = $('{v}: richiesta').first().json;
const err = $input.item.json.error;
if (/429|spacing/.test(String((err && (err.message || err)) || ''))) await new Promise(r => setTimeout(r, 8000));
return {{ json: {{ image_id: req.image_id, _attempt: (req._attempt || 0) + 1 }} }};
""", x + 880, y + 180),
        http_cv(f"{v}: gate", f"{cv_url}/gate_remote",
                "={{ JSON.stringify({ " + original_ref_expr + ", candidate_url: Array.isArray($json.output) ? $json.output[0] : $json.output, save_as: " + save_as_expr + " }) }}",
                x + 660, y),
        code(f"Record {v}", record_js_gen, x + 900, y),
    ]
    connect(connections, src, f"{v}: richiesta")
    chain(connections, [f"{v}: richiesta", f"{v}: Replicate", f"{v}: succeeded?"])
    connect(connections, f"{v}: succeeded?", f"{v}: gate", output=0)
    connect(connections, f"{v}: succeeded?", f"{v}: in corso?", output=1)
    connect(connections, f"{v}: in corso?", f"{v}: attendi", output=0)
    chain(connections, [f"{v}: attendi", f"{v}: stato", f"{v}: conta", f"{v}: succeeded?"])  # the polling loop
    connect(connections, f"{v}: in corso?", f"{v}: nsfw?", output=1)
    connect(connections, f"{v}: nsfw?", f"{v}: nuovo seed", output=0)
    connect(connections, f"{v}: nuovo seed", f"{v}: richiesta")  # the NSFW retry loop
    connect(connections, f"{v}: nsfw?", f"Record {v}", output=1)
    connect(connections, f"{v}: gate", f"Record {v}")
    return f"Record {v}"


# ---------------------------------------------------------------- product


def build_product() -> dict:
    cv_url = read_env("CV_SERVICE_PUBLIC_URL", "https://CHANGE-ME.ngrok-free.app")
    correct_id = read_env("N8N_CORRECT_WORKFLOW_ID", "PASTE-CORREGGI-WORKFLOW-ID")

    upload_js = """
// The upload arrives as binary on the webhook item; hand it to cv-service as base64.
const name = Object.keys($input.item.binary || {})[0];
if (!name) throw new Error('no file uploaded (expected multipart field "image")');
const buf = await this.helpers.getBinaryDataBuffer(0, name);
return { json: { image_b64: buf.toString('base64'), t0: Date.now() } };
"""
    respond_js = """
// The run record: the three versions in a RANDOM order with blind ids fixed here.
// Images are already on disk (Correggi and the gate saved them); cv-service
// assembles the cards from this record when the Prova view asks for the result.
const prep = $('Prepara').first().json;
const variants = ['D1', 'D2', 'D3'].map(v => $('Record ' + v).first().json.variants[0]);
const order = variants.map(v => v.variant).sort(() => Math.random() - 0.5);
return { json: { image_id: prep.image_id, source: 'live', judge: [], order,
  variants: variants.map(({ output_b64, ...rest }) => rest),
  input_warnings: prep.stats.input_warnings || [], heuristic_defects: prep.heuristic_defects,
  latency_ms: Date.now() - $('Upload').first().json.t0 } };
"""
    nodes = [
        sticky("Ingresso", "Upload dalla vista Prova. /prepare ritaglia le bande nere, limita la dimensione, misura la foto, calcola la diagnosi euristica (D1, e riserva se un modello non risponde) e salva l'originale preparato. Il webhook RISPONDE SUBITO con l'image_id: il generativo puo' metterci due minuti a freddo, il webhook di n8n Cloud si chiude a ~100 s.", -120, 180, 880, 300, 4),
        sticky("Tre famiglie di correzione", "D1 e D2 decidono COSA correggere e con quali valori, poi passano dallo stesso sub-workflow Correggi (un modulo per difetto, gate per modulo). D3 ridisegna i pixel in un colpo solo. Stesso gate di fedelta' per tutti: la scelta dell'agente misura il metodo, il gate misura il rischio.", 620, -140, 3000, 160, 7),
        sticky("Tre versioni, con scheda", "Il record fissa un ordine casuale (V1..V3, usato dallo Studio) e va in experiments/runs. Il sito, che ha gia' ricevuto l'image_id, chiede il risultato al workflow Scelte finche' non e' pronto e mostra le tre versioni affiancate con la scheda di ogni metodo. La preferenza si misura nello Studio, non qui.", 3900, 180, 900, 300, 2),
        node("Webhook", "n8n-nodes-base.webhook", 2, {
            "httpMethod": "POST", "path": "photo-lab-product", "responseMode": "responseNode",
            "options": {"allowedOrigins": "*"},
        }, -40, 320),
        code("Upload", upload_js, 180, 320),
        http_cv("Prepara", f"{cv_url}/prepare", "={{ JSON.stringify({ image_b64: $json.image_b64, save_as: 'live_' + $('Upload').first().json.t0 + '_orig', image_id: 'live_' + $('Upload').first().json.t0 }) }}", 400, 320),
        node("Rispondi subito", "n8n-nodes-base.respondToWebhook", 1.1, {
            "respondWith": "json", "responseBody": "={{ JSON.stringify({ accepted: true, image_id: $json.image_id }) }}",
            "options": {"responseHeaders": {"entries": [{"name": "Access-Control-Allow-Origin", "value": "*"}]}},
        }, 620, 320),
        node("Attendi le 3 versioni", "n8n-nodes-base.merge", 3, {"numberInputs": 3, "options": {}}, 3720, 420),
        code("Record", respond_js, 3960, 420, each_item=False),
        http_cv("Salva run", f"={cv_url}/runs/{{{{ $json.image_id }}}}", "={{ JSON.stringify($json) }}", 4200, 420),
    ]
    connections: dict = {}
    chain(connections, ["Webhook", "Upload", "Prepara", "Rispondi subito"])
    for i, (variant, (label, model, second_look)) in enumerate(DIAGNOSERS.items()):
        y = 120 + i * 320
        title, body, colour = LANE_NOTES[variant]
        nodes.append(sticky(title, body, 620, y - 100, 3000, 300, colour))
        record = diagnoser_lane(
            nodes, connections, variant=variant, label=label, model=model, second_look=second_look,
            src="Rispondi subito", x=920, y=y, correct_id=correct_id,
            image_expr="{ type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: $('Prepara').first().json.image_b64 } }",
            input_expr="{ image_b64: prep.image_b64 }", save_as_expr=f"prep.image_id + '_{variant}'",
            original_expr="{ type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: $('Prepara').first().json.image_b64 } }",
            corrected_expr="{ type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: r.output_b64 } }",
            chained_to=None)
        connect(connections, record, "Attendi le 3 versioni", index=i)
    y = 120 + len(DIAGNOSERS) * 320
    title, body, colour = LANE_NOTES[GENERATIVE]
    nodes.append(sticky(title, body, 620, y - 100, 3000, 300, colour))
    record = generative_lane(nodes, connections, src="Rispondi subito", x=920, y=y, cv_url=cv_url,
                             image_expr="`data:image/jpeg;base64,${$('D3: shrink').first().json.image_b64}`",
                             original_ref_expr="original_b64: $('Prepara').first().json.image_b64",
                             save_as_expr="$('Prepara').first().json.image_id + '_D3'", chained_to=None)
    # Replicate takes an inline image only up to ~256 KB: a 1024 px copy for the model,
    # the full-size original for the gate.
    nodes.append(http_cv("D3: shrink", f"{cv_url}/prepare", "={{ JSON.stringify({ image_b64: $('Prepara').first().json.image_b64, max_side: 1024 }) }}", 700, y))
    connections["Rispondi subito"]["main"][0] = [c for c in connections["Rispondi subito"]["main"][0] if c["node"] != "D3: richiesta"]
    chain(connections, ["Rispondi subito", "D3: shrink", "D3: richiesta"])
    connect(connections, record, "Attendi le 3 versioni", index=len(DIAGNOSERS))
    chain(connections, ["Attendi le 3 versioni", "Record", "Salva run"])
    return {"name": "photo-lab prodotto (Prova)", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}


# ----------------------------------------------------------------- choice


def build_choice() -> dict:
    """Tiny webhooks: record one blind judgement, serve the tally, list the study."""
    cv_url = read_env("CV_SERVICE_PUBLIC_URL", "https://CHANGE-ME.ngrok-free.app")
    cors = {"responseHeaders": {"entries": [{"name": "Access-Control-Allow-Origin", "value": "*"}]}}
    nodes = [
        sticky("Giudizio", "Le viste Prova e Studio mandano una risposta alla volta { image_id, task: realism|quality|best, variant, answer, shown, order, tester }. cv-service la accoda a experiments/judgments.csv.", -120, 100, 900, 260, 5),
        sticky("Tabellone", "La vista Esperimento chiede il riepilogo: per ogni workflow quante volte scelto su quante mostrate (intervallo di Wilson), costo, latenza, errori, bocciature del gate, guardie. E la regola di decisione applicata.", -120, 440, 900, 260, 3),
        node("Webhook scelta", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": "photo-lab-choice", "responseMode": "responseNode", "options": {"allowedOrigins": "*"}}, -40, 220),
        http_cv("Registra giudizio", f"{cv_url}/choices", "={{ JSON.stringify($json.body) }}", 200, 220),
        node("Rispondi scelta", "n8n-nodes-base.respondToWebhook", 1.1, {"respondWith": "json", "responseBody": "={{ JSON.stringify($json) }}", "options": cors}, 440, 220),
        node("Webhook tabellone", "n8n-nodes-base.webhook", 2, {"httpMethod": "GET", "path": "photo-lab-summary", "responseMode": "responseNode", "options": {"allowedOrigins": "*"}}, -40, 560),
        http_cv("Riepilogo", f"{cv_url}/summary", None, 200, 560, method="GET"),
        node("Rispondi tabellone", "n8n-nodes-base.respondToWebhook", 1.1, {"respondWith": "json", "responseBody": "={{ JSON.stringify($json) }}", "options": cors}, 440, 560),
        sticky("Risultato", "La Prova ha ricevuto l'image_id subito; qui chiede ogni 5 s se il record e' pronto. cv-service risponde 404 finche' il prodotto non ha salvato il run, poi le tre schede con le immagini.", -120, 780, 900, 260, 6),
        node("Webhook risultato", "n8n-nodes-base.webhook", 2, {"httpMethod": "GET", "path": "photo-lab-result", "responseMode": "responseNode", "options": {"allowedOrigins": "*"}}, -40, 900),
        node("Schede", "n8n-nodes-base.httpRequest", 4.2, {"method": "GET", "url": f"={cv_url}/runs/{{{{ $json.query.image_id }}}}/cards", "options": {"timeout": 60000}}, 200, 900, onError="continueRegularOutput"),
        node("Rispondi risultato", "n8n-nodes-base.respondToWebhook", 1.1, {"respondWith": "json", "responseBody": "={{ JSON.stringify($json.ready ? $json : { ready: false }) }}", "options": cors}, 440, 900),
    ]
    nodes += [
        sticky("Studio", "La vista Studio chiede la lista delle foto dello studio cieco (experiments/study-set.txt) e quali hanno gia' le tre versioni pronte.", 1000, 100, 700, 260, 2),
        node("Webhook studio", "n8n-nodes-base.webhook", 2, {"httpMethod": "GET", "path": "photo-lab-study", "responseMode": "responseNode", "options": {"allowedOrigins": "*"}}, 1080, 220),
        http_cv("Lista studio", f"{cv_url}/study", None, 1320, 220, method="GET"),
        node("Rispondi studio", "n8n-nodes-base.respondToWebhook", 1.1, {"respondWith": "json", "responseBody": "={{ JSON.stringify($json) }}", "options": cors}, 1560, 220),
    ]
    connections: dict = {}
    chain(connections, ["Webhook scelta", "Registra giudizio", "Rispondi scelta"])
    chain(connections, ["Webhook tabellone", "Riepilogo", "Rispondi tabellone"])
    chain(connections, ["Webhook risultato", "Schede", "Rispondi risultato"])
    chain(connections, ["Webhook studio", "Lista studio", "Rispondi studio"])
    return {"name": "photo-lab scelte (Esperimento)", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}


# ------------------------------------------------------------------ batch


def build_batch() -> dict:
    """The same three lanes on the dataset photos, one at a time, to prepare the
    versions the Studio shows. Same lanes, same Correggi as the product."""
    cv_url = read_env("CV_SERVICE_PUBLIC_URL", "https://CHANGE-ME.ngrok-free.app")
    correct_id = read_env("N8N_CORRECT_WORKFLOW_ID", "PASTE-CORREGGI-WORKFLOW-ID")
    finalize_js = """
// The record of one dataset photo: the three versions in a random order (the blind
// order the Studio shows them in), then saved like a product run.
const rec = $input.item.json;
const order = rec.variants.map(v => v.variant).sort(() => Math.random() - 0.5);
return { json: { ...rec, source: 'batch', order, judge: [] } };
"""
    nodes = [
        sticky("Setup e ciclo", "Una foto etichettata per iterazione: ogni record e' salvato prima di passare alla successiva, cosi' un'interruzione non perde il lavoro fatto. Config: ids = lo studio (le foto scelte a mano). /prepare misura la foto una volta per tutte le famiglie.", -120, -160, 1900, 420, 4),
        sticky("Le stesse tre corsie del prodotto", "Stessa diagnosi, stesso Correggi, stesso generativo. Qui in sequenza (una foto alla volta) e con le etichette a mano: la diagnosi si misura anche con precision/recall per difetto.", 1800, -160, 3300, 160, 7),
        sticky("GIUDICE - pairwise, cieco", "Al posto dell'agente: Sonnet confronta le tre coppie, 3 volte con lati casuali. Output identici = 'indistinguibile' senza chiamata. Voti non unanimi = 'indistinguibile'.", 1800, 1340, 1900, 360, 7),
        node("Manual Trigger", "n8n-nodes-base.manualTrigger", 1, {}, -40, 40),
        node("Config", "n8n-nodes-base.set", 3.4, {
            "assignments": {"assignments": [
                {"id": "cv", "name": "cv_url", "value": cv_url, "type": "string"},
                {"id": "lim", "name": "limit", "value": 60, "type": "number"},
                {"id": "skip", "name": "skip_done", "value": True, "type": "boolean"},
                # study set: only these ids (empty = the whole dataset)
                {"id": "ids", "name": "ids", "value": ",".join(STUDY_IDS), "type": "string"},
            ]},
            "options": {},
        }, 180, 40),
        node("List images", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "GET",
            "url": "={{ $json.cv_url }}/dataset",
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "limit", "value": "={{ $json.limit }}"},
                {"name": "skip_done", "value": "={{ $json.skip_done }}"},
            ]},
            "options": {"timeout": 60000},
        }, 400, 40),
        code("Split images", """
// Optional id list from Config (the study set); otherwise every image the API returned.
const want = String($('Config').first().json.ids || '').split(',').map(s => s.trim()).filter(Boolean);
return $input.first().json.images.filter(i => !want.length || want.includes(i.image_id)).map(i => ({ json: i }));
""", 620, 40, each_item=False),
        node("Loop", "n8n-nodes-base.splitInBatches", 3, {"batchSize": 1, "options": {}}, 840, 40),
        node("Done", "n8n-nodes-base.noOp", 1, {}, 1060, -60),
        node("Current image", "n8n-nodes-base.set", 3.4, {
            "assignments": {"assignments": [{"id": "id", "name": "image_id", "value": "={{ $json.image_id }}", "type": "string"}]},
            "options": {},
        }, 1060, 140),
        http_cv("Prepara", f"{cv_url}/prepare", "={{ JSON.stringify({ image_id: $json.image_id, max_side: 1024 }) }}", 1300, 140),
    ]
    connections: dict = {}
    chain(connections, ["Manual Trigger", "Config", "List images", "Split images", "Loop"])
    connect(connections, "Loop", "Done", output=0)
    connect(connections, "Loop", "Current image", output=1)
    chain(connections, ["Current image", "Prepara"])

    prev_record: str | None = None
    src = "Prepara"
    for i, (variant, (label, model, second_look)) in enumerate(DIAGNOSERS.items()):
        y = 120 + i * 300
        title, body, colour = LANE_NOTES[variant]
        nodes.append(sticky(title, body, 1800, y - 100, 3300, 280, colour))
        record = diagnoser_lane(
            nodes, connections, variant=variant, label=label, model=model, second_look=second_look,
            src=src, x=1900, y=y, correct_id=correct_id,
            image_expr="{ type: 'image', source: { type: 'url', url: `${$('Config').first().json.cv_url}/dataset/${$('Current image').first().json.image_id}/file?max_side=1024` } }",
            input_expr="{ image_id: prep.image_id }", save_as_expr=f"prep.image_id + '_{variant}'",
            original_expr="{ type: 'image', source: { type: 'url', url: `${$('Config').first().json.cv_url}/dataset/${image_id}/file?max_side=1024` } }",
            corrected_expr=f"{{ type: 'image', source: {{ type: 'url', url: `${{$('Config').first().json.cv_url}}/processed/${{image_id}}_{variant}.jpg?max_side=1024&v=${{Date.now()}}` }} }}",
            chained_to=prev_record)
        prev_record = record
        src = record  # sequential: one photo at a time through the free tunnel
    y = 120 + len(DIAGNOSERS) * 300
    title, body, colour = LANE_NOTES[GENERATIVE]
    nodes.append(sticky(title, body, 1800, y - 100, 3300, 280, colour))
    prev_record = generative_lane(nodes, connections, src=src, x=1900, y=y, cv_url=cv_url,
                                  image_expr="`${$('Config').first().json.cv_url}/dataset/${prep.image_id}/file?max_side=1024`",
                                  original_ref_expr="image_id: $('Prepara').first().json.image_id",
                                  save_as_expr="$('Prepara').first().json.image_id + '_D3'", chained_to=prev_record)

    nodes += [
        code("Record", finalize_js, 1900, 1480),
        http_cv("Save run", f"={cv_url}/runs/{{{{ $json.image_id }}}}", "={{ JSON.stringify($json) }}", 2120, 1480),
    ]
    chain(connections, [prev_record, "Record", "Save run", "Loop"])
    return {"name": "photo-lab esperimento su dataset (batch)", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}


if __name__ == "__main__":
    OUT["choice"] = ROOT / "n8n" / "workflow-choice.json"
    for name, build in (("correct", build_correct), ("product", build_product), ("choice", build_choice), ("batch", build_batch)):
        OUT[name].write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"-> {OUT[name].relative_to(ROOT)}")
