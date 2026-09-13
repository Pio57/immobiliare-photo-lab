"""The experiment that lives inside the product.

Every upload in the Prova view runs the three families and saves one record in
experiments/runs/ (via /runs); the agent's blind choice lands in
experiments/choices.csv (via /choices). /summary turns both into the numbers the
Esperimento view shows and applies the decision rule. Nothing here is simulated:
the numbers grow with use."""

from __future__ import annotations

import csv
import json
import math
import statistics
import time
from pathlib import Path

import base64

import cv2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.dataset import raw_image_path
from app.config import settings
from app.core import pipeline

router = APIRouter(tags=["experiment"])

VARIANTS = ["D1", "D2", "D3"]
LABELS = {"D1": "Regole", "D2": "Haiku + verifica", "D3": "Generativo"}
MIN_CHOICES = 30  # below this the tally is shown but no winner is declared
DEFECT_ALIASES = {"tungsten_cast": "color_cast"}  # labels.csv vocabulary -> diagnosis vocabulary


def _root() -> Path:
    return Path(settings.repo_root).resolve()


def _choices_path() -> Path:
    return _root() / "experiments" / "choices.csv"


class Choice(BaseModel):
    image_id: str
    chosen: str | None  # a variant id; None = "keep the original"; "tie" = pair indistinguishable (study)
    shown: list[str]
    order: list[str] = []  # the blind order the cards were displayed in
    tester: str = ""  # study: who chose (initials); empty for the Prova view


@router.get("/study")
def study() -> dict:
    """The blind study: the hand-picked photo ids, which ones have a saved record,
    and how many testers have completed choices so far."""
    ids_path = _root() / "experiments" / "study-set.txt"
    ids = ids_path.read_text(encoding="utf-8").split() if ids_path.exists() else []
    runs_dir = _root() / "experiments" / "runs"
    ready = [i for i in ids if (runs_dir / f"{i}.json").exists()]
    testers: dict[str, int] = {}
    if _choices_path().exists():
        with _choices_path().open(encoding="utf-8") as f:
            for c in csv.DictReader(f):
                if c.get("tester"):
                    testers[c["tester"]] = testers.get(c["tester"], 0) + 1
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

    def data_url(name: str) -> str | None:
        f = processed / f"{name}.jpg"
        return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode("ascii") if f.exists() else None

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
def save_choice(choice: Choice) -> dict:
    path = _choices_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "image_id", "chosen", "shown", "order", "tester"])
        w.writerow([int(time.time()), choice.image_id, choice.chosen or "", ";".join(choice.shown), ";".join(choice.order), choice.tester])
    return {"saved": True, "choices": sum(1 for _ in path.open(encoding="utf-8")) - 1}


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
    records = []
    for p in sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []:
        try:
            records.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    choices = []
    if _choices_path().exists():
        with _choices_path().open(encoding="utf-8") as f:
            choices = list(csv.DictReader(f))

    per: dict[str, dict] = {v: {"variant": v, "label": LABELS[v], "runs": 0, "shown": 0, "chosen": 0, "cost": [], "latency": [],
                                "errors": 0, "fixes": 0, "gate_rejected": 0, "modules_run": 0, "unchanged": 0, "ai": 0,
                                "crop": [], "fidelity": [], "keep": 0, "second_look": 0, "diag": {"tp": 0, "fp": 0, "fn": 0, "n": 0}}
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
                found = {DEFECT_ALIASES.get(d, d) for d in (v.get("defects") or [])} & {"underexposed", "backlit", "color_cast", "noise", "tilt", "low_resolution"}
                truth = truth & {"underexposed", "backlit", "color_cast", "noise", "tilt", "low_resolution"}
                s["diag"]["tp"] += len(found & truth)
                s["diag"]["fp"] += len(found - truth)
                s["diag"]["fn"] += len(truth - found)
                s["diag"]["n"] += 1
    keep_original = ties = 0
    for c in choices:
        for v in c["shown"].split(";"):
            if v in per:
                per[v]["shown"] += 1
        if c["chosen"] in per:
            per[c["chosen"]]["chosen"] += 1
        elif c["chosen"] == "tie":  # study pair judged indistinguishable
            ties += 1
        elif not c["chosen"]:
            keep_original += 1

    rows = []
    for v in VARIANTS:
        s = per[v]
        d = s["diag"]
        precision = d["tp"] / (d["tp"] + d["fp"]) if d["tp"] + d["fp"] else None
        recall = d["tp"] / (d["tp"] + d["fn"]) if d["tp"] + d["fn"] else None
        lo, hi = _wilson(s["chosen"], s["shown"])
        rows.append({
            "variant": v, "label": s["label"], "runs": s["runs"], "shown": s["shown"], "chosen": s["chosen"],
            "choice_share": round(s["chosen"] / s["shown"], 3) if s["shown"] else None, "choice_ci": [lo, hi],
            "cost_mean_usd": round(statistics.mean(s["cost"]), 5) if s["cost"] else 0.0,
            "latency_p50_ms": int(_pct(s["latency"], 0.5)), "latency_p95_ms": int(_pct(s["latency"], 0.95)),
            "error_rate": round(s["errors"] / s["runs"], 3) if s["runs"] else 0.0,
            "fixes_rate": round(s["fixes"] / s["runs"], 3) if s["runs"] else 0.0,
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

    # ---- decision rule, applied to the numbers above
    n_choices = len(choices)
    eligible = [r for r in rows if r["runs"] > 0 and r["error_rate"] <= 0.10 and r["gate_rejected_rate"] <= 0.10]
    excluded = [{"variant": r["variant"], "why": "tasso di errore oltre il 10%" if r["error_rate"] > 0.10 else "oltre il 10% delle correzioni bocciate dal controllo di fedeltà"}
                for r in rows if r["runs"] > 0 and r not in eligible]
    verdict: dict = {"n_choices": n_choices, "min_choices": MIN_CHOICES, "excluded": excluded, "winner": None, "tie": [], "reason": ""}
    ranked = sorted([r for r in eligible if r["shown"]], key=lambda r: -(r["choice_share"] or 0))
    if n_choices < MIN_CHOICES:
        verdict["reason"] = f"Raccolti {n_choices} giudizi su un minimo di {MIN_CHOICES}: il campione è ancora troppo piccolo per una decisione."
    elif ranked:
        top = ranked[0]
        tied = [r for r in ranked if r["choice_ci"][1] >= top["choice_ci"][0]]  # overlapping confidence intervals
        if len(tied) == 1:
            verdict["winner"] = top["variant"]
            verdict["reason"] = (f"{top['label']} è preferito nel {round(100 * top['choice_share'])}% dei confronti in cui compare, "
                                 f"e il vantaggio è statisticamente significativo (intervalli di confidenza al 95% non sovrapposti).")
        else:
            cheapest = min(tied, key=lambda r: (r["cost_mean_usd"], r["latency_p50_ms"]))
            verdict["winner"] = cheapest["variant"]
            verdict["tie"] = [r["variant"] for r in tied]
            verdict["reason"] = (f"Tra {' e '.join(r['label'] for r in tied)} la differenza di preferenza non è statisticamente "
                                 f"significativa (intervalli di confidenza al 95% sovrapposti). A parità di qualità percepita "
                                 f"la scelta va al metodo più economico e più rapido: {cheapest['label']}.")
    return {
        "generated_at": int(time.time()), "runs": len(records), "choices": n_choices,
        "keep_original_choices": keep_original, "ties": ties,
        "keep_original_share": round(keep_original / n_choices, 3) if n_choices else None,
        "variants": rows, "verdict": verdict,
        "decision_rule": [
            "Requisito di ammissione: tasso di errore e quota di correzioni bocciate dal controllo di fedeltà entrambi sotto il 10%. Un metodo che altera l'immobile non entra in gara, qualunque sia la sua qualità percepita.",
            f"Tra i metodi ammessi vince la preferenza degli utenti nel test cieco. Sotto {MIN_CHOICES} giudizi il campione non basta e non si decide.",
            "Se gli intervalli di confidenza al 95% si sovrappongono, la differenza non è significativa: a parità di qualità percepita si sceglie il metodo con costo per foto più basso, poi quello più rapido.",
        ],
    }
