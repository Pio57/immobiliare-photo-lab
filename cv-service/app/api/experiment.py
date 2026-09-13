"""The experiment that lives inside the product.

Every upload in the Prova view runs the three families and saves one record in
experiments/runs/ (via /runs). Human judgements land in experiments/judgments.csv
(via /choices): the blind study of the Studio view asks, for every photo, whether
each version looks altered (realism), how good it looks on its own (quality, 1-5)
and which of the three the tester would publish (best); the Prova view records the
agent's own "best" on a fresh photo. /summary turns runs and judgements into the
numbers the Esperimento view shows and applies the decision rule. Nothing here is
simulated: the numbers grow with use."""

from __future__ import annotations

import base64
import csv
import json
import math
import statistics
import time
from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.dataset import raw_image_path
from app.config import settings
from app.core import pipeline

router = APIRouter(tags=["experiment"])

VARIANTS = ["D1", "D2", "D3"]
LABELS = {"D1": "Regole", "D2": "Haiku + verifica", "D3": "Generativo"}
TASKS = ("realism", "quality", "best")
MIN_BEST = 30  # "best" judgements needed before a winner is declared
MIN_REALISM = 10  # realism answers per variant before the alteration rate can exclude it
MAX_ALTERATION = 0.10  # admission thresholds of the decision rule
MAX_GATE_REJECTED = 0.10
MAX_ERRORS = 0.10
DEFECT_ALIASES = {"tungsten_cast": "color_cast"}  # labels.csv vocabulary -> diagnosis vocabulary
EFFECTIVE_MIN_QUALITY = 4  # "output efficace": rated good or better, and not seen as altered
DIAG_SET = {"underexposed", "overexposed", "backlit", "color_cast", "noise", "tilt", "rotated", "low_resolution"}


def _root() -> Path:
    return Path(settings.repo_root).resolve()


def _judgments_path() -> Path:
    return _root() / "experiments" / "judgments.csv"


class Judgment(BaseModel):
    """One answer of one tester on one photo.

    task=realism: variant = the version shown next to the original, answer = "yes" (looks
    altered) | "no". task=quality: variant = the version shown alone, answer = "1".."5".
    task=best: variant = the chosen version, "" = keeps the original; shown = the versions
    on screen. tester = initials ("" from the Prova view)."""

    image_id: str
    task: str
    variant: str = ""
    answer: str = ""
    shown: list[str] = []
    order: list[str] = []
    tester: str = ""


def _read_judgments() -> list[dict]:
    path = _judgments_path()
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@router.get("/study")
def study() -> dict:
    """The blind study: the hand-picked photo ids, which ones have a saved record,
    and how many answers each tester has given so far."""
    ids_path = _root() / "experiments" / "study-set.txt"
    ids = ids_path.read_text(encoding="utf-8").split() if ids_path.exists() else []
    runs_dir = _root() / "experiments" / "runs"
    ready = [i for i in ids if (runs_dir / f"{i}.json").exists()]
    testers: dict[str, int] = {}
    for j in _read_judgments():
        if j.get("tester"):
            testers[j["tester"]] = testers.get(j["tester"], 0) + 1
    return {"ids": ids, "ready": ready, "testers": testers}


@router.get("/runs/{image_id}/cards")
def cards(image_id: str) -> dict:
    """The async result of one upload: the saved record plus the output images,
    in the blind order the record fixed. 404 until the product workflow has saved it."""
    path = _root() / "experiments" / "runs" / f"{image_id}.json"
    if not path.exists():
        raise HTTPException(404, "not ready")
    rec = json.loads(path.read_text(encoding="utf-8"))
    processed = _root() / "dataset" / "processed"
    # generated images are not versioned; the site snapshot (which is) doubles as the
    # fallback, so a fresh clone on a server can serve the study without a batch run
    fallbacks = [_root() / "snapshot" / "img", _root() / "frontend" / "public" / "snapshot" / "img"]

    def data_url(name: str) -> str | None:
        for folder in [processed, *fallbacks]:
            f = folder / f"{name}.jpg"
            if f.exists():
                return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode("ascii")
        return None

    by_id = {v["variant"]: v for v in rec.get("variants", [])}
    order = [v for v in rec.get("order") or list(by_id) if v in by_id]
    cards_out = []
    for i, vid in enumerate(order):
        v = by_id[vid]
        output = data_url(f"{image_id}_{vid}") if v.get("status") in ("accepted", "rejected_fidelity") else None
        cards_out.append({
            "blind_id": f"V{i + 1}", "variant": vid, "label": v.get("label"), "model": v.get("model"), "source": v.get("source"),
            "status": v.get("status"), "output": output, "changed": v.get("status") != "unchanged" and output is not None,
            "ai_reconstructed": bool(v.get("ai_reconstructed")), "crop_pct": v.get("crop_pct") or 0,
            "fidelity": v.get("fidelity"), "params": v.get("params"), "steps": v.get("steps") or [],
            "diagnosis": {"source": v.get("source"), "model": v.get("model"), "defects": v.get("defects") or [],
                          "advice": v.get("advice") or [], "reason": v.get("reason") or "", "recommendation": v.get("recommendation") or "apply",
                          "plan_fixes": v.get("plan_fixes") or [], "review_verdict": v.get("review_verdict"),
                          "cost_usd": v.get("cost_usd") or 0, "latency_ms": v.get("latency_ms") or 0, "error": v.get("error"),
                          "heuristic_defects": rec.get("heuristic_defects") or []},
            "cost_usd": v.get("cost_usd") or 0, "latency_ms": v.get("latency_ms") or 0, "iterations": v.get("iterations") or 1,
            "error": v.get("error"), "measured_changes": v.get("measured_changes"),
        })
    original = data_url(f"{image_id}_orig")
    if original is None:  # a dataset photo (study set): the original is the raw file, bounded like the outputs
        try:
            raw = cv2.imread(str(raw_image_path(image_id)))
            raw = pipeline.trim_uniform_borders(raw)
            h, w = raw.shape[:2]
            scale = min(1.0, settings.max_side / max(h, w))
            if scale < 1:
                raw = cv2.resize(raw, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
            original = "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", raw, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()).decode("ascii")
        except Exception:  # noqa: BLE001
            original = None
    return {"ready": True, "image_id": image_id, "original": original, "cards": cards_out, "order": order,
            "input_warnings": rec.get("input_warnings") or [], "latency_ms": rec.get("latency_ms") or 0}


@router.post("/choices")
def save_judgment(j: Judgment) -> dict:
    """Append one judgement. The route keeps its historical name: the n8n webhook
    'photo-lab-choice' points here."""
    if j.task not in TASKS:
        raise HTTPException(422, f"task must be one of {TASKS}")
    if j.task == "quality" and j.answer not in {"1", "2", "3", "4", "5"}:
        raise HTTPException(422, "quality answer must be 1..5")
    if j.task == "realism" and j.answer not in {"yes", "no"}:
        raise HTTPException(422, "realism answer must be yes|no")
    path = _judgments_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "tester", "image_id", "task", "variant", "answer", "shown", "order"])
        w.writerow([int(time.time()), j.tester, j.image_id, j.task, j.variant, j.answer, ";".join(j.shown), ";".join(j.order)])
    return {"saved": True, "judgments": sum(1 for _ in path.open(encoding="utf-8")) - 1}


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 3), round(c + h, 3)


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return float(s[min(len(s) - 1, int(round(q * (len(s) - 1))))])


def _labels() -> dict[str, set[str]]:
    path = _root() / "dataset" / "raw" / "labels.csv"
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tags = {DEFECT_ALIASES.get(t, t) for t in r["defects"].split(";") if t and t != "ok"}
            out[r["image_id"]] = tags
    return out


@router.get("/summary")
def summary() -> dict:
    runs_dir = _root() / "experiments" / "runs"
    # the experiment is the study set (experiments/study-set.txt); uploads from the Prova
    # view are product usage and stay out of the tally
    ids_path = _root() / "experiments" / "study-set.txt"
    study_ids = set(ids_path.read_text(encoding="utf-8").split()) if ids_path.exists() else None
    records = []
    for p in sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []:
        if study_ids is not None and p.stem not in study_ids:
            continue
        try:
            records.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    judgments = _read_judgments()

    per: dict[str, dict] = {v: {"variant": v, "label": LABELS[v], "runs": 0, "cost": [], "latency": [],
                                "errors": 0, "fixes": 0, "gate_rejected": 0, "modules_run": 0, "unchanged": 0, "ai": 0,
                                "crop": [], "fidelity": [], "keep": 0, "second_look": 0, "fallback": 0,
                                "diag": {"tp": 0, "fp": 0, "fn": 0, "n": 0},
                                "realism_n": 0, "altered": 0, "quality": [], "shown": 0, "chosen": 0,
                                "altered_by": {}, "quality_by": {}}
                            for v in VARIANTS}
    labels = _labels()
    for rec in records:
        for v in rec.get("variants", []):
            s = per.get(v.get("variant"))
            if not s:
                continue
            s["runs"] += 1
            s["cost"].append(float(v.get("cost_usd") or 0) + sum(float((st.get("params") or {}).get("cost_usd") or 0) for st in v.get("steps") or []))
            s["latency"].append(float(v.get("latency_ms") or 0))
            s["errors"] += 1 if v.get("status") == "error" else 0
            # a model family that answered with the rules' plan: the model failed and the product fell back
            s["fallback"] += 1 if v.get("variant") != "D1" and v.get("source") == "heuristic" else 0
            s["fixes"] += 1 if v.get("plan_fixes") else 0
            steps = v.get("steps") or []
            s["modules_run"] += sum(1 for st in steps if st.get("needed"))
            s["gate_rejected"] += sum(1 for st in steps if st.get("needed") and not st.get("applied"))
            s["unchanged"] += 1 if v.get("status") == "unchanged" else 0
            s["ai"] += 1 if v.get("ai_reconstructed") else 0
            s["keep"] += 1 if v.get("recommendation") == "keep_original" else 0
            s["second_look"] += 1 if v.get("review_verdict") == "adjust" else 0
            if v.get("crop_pct"):
                s["crop"].append(float(v["crop_pct"]))
            if v.get("fidelity") and v["fidelity"].get("score") is not None:
                s["fidelity"].append(float(v["fidelity"]["score"]))
            truth = labels.get(rec.get("image_id"))
            if truth is not None:
                if v.get("variant") != "D3":  # the generative family does not diagnose
                    found = {DEFECT_ALIASES.get(d, d) for d in (v.get("defects") or [])} & DIAG_SET
                    t = truth & DIAG_SET
                    s["diag"]["tp"] += len(found & t)
                    s["diag"]["fp"] += len(found - t)
                    s["diag"]["fn"] += len(t - found)
                    s["diag"]["n"] += 1

    n_best = keep_original = 0
    for j in judgments:
        task = j.get("task")
        key = (j.get("tester"), j.get("image_id"))
        if task == "realism" and j.get("variant") in per:
            s = per[j["variant"]]
            s["realism_n"] += 1
            s["altered"] += 1 if j.get("answer") == "yes" else 0
            s["altered_by"][key] = j.get("answer") == "yes"
        elif task == "quality" and j.get("variant") in per and (j.get("answer") or "").isdigit():
            s = per[j["variant"]]
            s["quality"].append(int(j["answer"]))
            s["quality_by"][key] = int(j["answer"])
        elif task == "best":
            n_best += 1
            for v in (j.get("shown") or "").split(";"):
                if v in per:
                    per[v]["shown"] += 1
            if j.get("variant") in per:
                per[j["variant"]]["chosen"] += 1
            else:
                keep_original += 1

    rows = []
    for v in VARIANTS:
        s = per[v]
        d = s["diag"]
        precision = d["tp"] / (d["tp"] + d["fp"]) if d["tp"] + d["fp"] else None
        recall = d["tp"] / (d["tp"] + d["fn"]) if d["tp"] + d["fn"] else None
        lo, hi = _wilson(s["chosen"], s["shown"])
        alo, ahi = _wilson(s["altered"], s["realism_n"])
        # "output efficace" is derived from the same tester's two answers on the same version:
        # publishable as is = rated good or better and not seen as altered
        paired = [k for k in s["quality_by"] if k in s["altered_by"]]
        eff_ok = sum(1 for k in paired if s["quality_by"][k] >= EFFECTIVE_MIN_QUALITY and not s["altered_by"][k])
        rows.append({
            "variant": v, "label": s["label"], "runs": s["runs"],
            # the four measures of phase 1
            "realism_n": s["realism_n"], "altered": s["altered"],
            "alteration_rate": round(s["altered"] / s["realism_n"], 3) if s["realism_n"] else None, "alteration_ci": [alo, ahi],
            "quality_n": len(s["quality"]), "mos": round(statistics.mean(s["quality"]), 2) if s["quality"] else None,
            "mos_sd": round(statistics.pstdev(s["quality"]), 2) if len(s["quality"]) > 1 else None,
            "shown": s["shown"], "chosen": s["chosen"],
            "choice_share": round(s["chosen"] / s["shown"], 3) if s["shown"] else None, "choice_ci": [lo, hi],
            "effective_n": len(paired), "effective_rate": round(eff_ok / len(paired), 3) if paired else None,
            # cost, time, reliability, risk
            "cost_mean_usd": round(statistics.mean(s["cost"]), 5) if s["cost"] else 0.0,
            "latency_p50_ms": int(_pct(s["latency"], 0.5)), "latency_p95_ms": int(_pct(s["latency"], 0.95)),
            "error_rate": round(s["errors"] / s["runs"], 3) if s["runs"] else 0.0,
            "fixes_rate": round(s["fixes"] / s["runs"], 3) if s["runs"] else 0.0,
            "fallback_rate": round(s["fallback"] / s["runs"], 3) if s["runs"] else 0.0,
            "gate_rejected_rate": round(s["gate_rejected"] / s["modules_run"], 3) if s["modules_run"] else 0.0,
            "unchanged_rate": round(s["unchanged"] / s["runs"], 3) if s["runs"] else 0.0,
            "keep_original_rate": round(s["keep"] / s["runs"], 3) if s["runs"] else 0.0,
            "second_look_rate": round(s["second_look"] / s["runs"], 3) if s["runs"] else 0.0,
            "ai_reconstructed_rate": round(s["ai"] / s["runs"], 3) if s["runs"] else 0.0,
            "crop_mean_pct": round(statistics.mean(s["crop"]), 1) if s["crop"] else 0.0,
            "fidelity_min": round(min(s["fidelity"]), 3) if s["fidelity"] else None,
            "fidelity_mean": round(statistics.mean(s["fidelity"]), 3) if s["fidelity"] else None,
            "diagnosis": {"n_labelled": d["n"], "precision": round(precision, 3) if precision is not None else None,
                          "recall": round(recall, 3) if recall is not None else None,
                          "f1": round(2 * precision * recall / (precision + recall), 3) if precision and recall else None},
        })

    # ---- decision rule (the funnel of the note), applied to the numbers above
    excluded = []
    eligible = []
    for r in rows:
        if r["runs"] == 0:
            continue
        why = None
        if r["error_rate"] > MAX_ERRORS:
            why = f"tasso di errore oltre il {round(MAX_ERRORS * 100)}%"
        elif r["gate_rejected_rate"] > MAX_GATE_REJECTED:
            why = f"oltre il {round(MAX_GATE_REJECTED * 100)}% delle correzioni bocciate dal controllo di fedeltà"
        elif r["realism_n"] >= MIN_REALISM and (r["alteration_rate"] or 0) > MAX_ALTERATION:
            why = f"oltre il {round(MAX_ALTERATION * 100)}% dei valutatori ha visto elementi alterati"
        if why:
            excluded.append({"variant": r["variant"], "why": why})
        else:
            eligible.append(r)
    verdict: dict = {"n_choices": n_best, "min_choices": MIN_BEST, "excluded": excluded, "winner": None, "tie": [], "reason": ""}
    ranked = sorted([r for r in eligible if r["shown"]], key=lambda r: -(r["choice_share"] or 0))
    if n_best < MIN_BEST:
        verdict["reason"] = f"Raccolti {n_best} giudizi di «foto migliore» su un minimo di {MIN_BEST}: il campione è ancora troppo piccolo per una decisione."
    elif not ranked:
        verdict["reason"] = "Nessun metodo supera i requisiti di ammissione."
    else:
        top = ranked[0]
        tied = [r for r in ranked if r["choice_ci"][1] >= top["choice_ci"][0]]  # overlapping confidence intervals
        if len(tied) == 1:
            verdict["winner"] = top["variant"]
            verdict["reason"] = (f"{top['label']} è la foto migliore nel {round(100 * top['choice_share'])}% dei giudizi in cui compare, "
                                 f"e il vantaggio è statisticamente significativo (intervalli di confidenza al 95% non sovrapposti).")
        else:
            cheapest = min(tied, key=lambda r: r["cost_mean_usd"])
            verdict["winner"] = cheapest["variant"]
            verdict["tie"] = [r["variant"] for r in tied]
            verdict["reason"] = (f"Tra {' e '.join(r['label'] for r in tied)} la differenza di preferenza non è statisticamente "
                                 f"significativa (intervalli di confidenza al 95% sovrapposti). A parità di qualità percepita "
                                 f"la scelta va al metodo più economico: {cheapest['label']}.")
    testers = {j["tester"] for j in judgments if j.get("tester")}
    return {
        "generated_at": int(time.time()), "runs": len(records), "judgments": len(judgments), "testers": len(testers),
        "choices": n_best, "keep_original_choices": keep_original,
        "keep_original_share": round(keep_original / n_best, 3) if n_best else None,
        "variants": rows, "verdict": verdict,
        "decision_rule": [
            f"Requisito di ammissione: tasso di errore e quota di correzioni bocciate dal controllo di fedeltà sotto il {round(MAX_GATE_REJECTED * 100)}%, "
            f"e meno del {round(MAX_ALTERATION * 100)}% di risposte «alterata» nella domanda sul realismo. Un metodo che altera l'immobile non entra in gara, qualunque sia la sua qualità.",
            f"Tra i metodi ammessi vince la foto migliore secondo i valutatori. Sotto {MIN_BEST} giudizi il campione non basta e non si decide; il voto di qualità (1-5) e l'output efficace descrivono il risultato ma non decidono.",
            "Se gli intervalli di confidenza al 95% si sovrappongono, la differenza non è significativa: a parità di qualità percepita si sceglie il metodo con costo per foto più basso. Il tempo di elaborazione non entra nella decisione: la correzione gira in background, una volta per annuncio.",
        ],
    }
