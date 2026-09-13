from fastapi.testclient import TestClient

from app.core.image_io import decode_b64, encode_b64
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_enhance_roundtrip(dark_room):
    res = client.post("/enhance", json={"image_b64": encode_b64(dark_room)})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["params"]["gamma"] < 1.0
    assert body["fidelity"]["passed"] is True
    assert decode_b64(body["image_b64"]).shape[:2] == dark_room.shape[:2]
    assert body["suggested_conservative_params"] is None


def test_apply_with_explicit_params(room):
    res = client.post("/apply", json={"image_b64": encode_b64(room), "params": {"gamma": 0.8, "rotate_deg": 2}})
    assert res.status_code == 200, res.text
    assert res.json()["params"]["rotate_deg"] == 2.0


def test_fidelity_endpoint(room):
    b = encode_b64(room)
    res = client.post("/fidelity", json={"original_b64": b, "candidate_b64": b})
    assert res.status_code == 200 and res.json()["passed"] is True


def test_bad_payload_is_422():
    assert client.post("/enhance", json={"image_b64": "bm90IGFuIGltYWdl"}).status_code == 422


def test_dataset_bridge_roundtrip(tmp_path, monkeypatch):
    from app.config import settings

    (tmp_path / "dataset" / "raw").mkdir(parents=True)
    (tmp_path / "dataset" / "raw" / "labels.csv").write_text("image_id,filename,defects\nimg_001,img_001.jpg,tilt\n")
    (tmp_path / "dataset" / "raw" / "img_001.jpg").write_bytes(b"\xff\xd8fake")
    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    assert client.get("/dataset").json()["count"] == 1
    assert client.get("/dataset/img_001").json()["labels"]["defects"] == "tilt"
    res = client.post("/runs/img_001", json={"image_id": "img_001", "variants": [{"variant": "D1", "image_b64": "aGk=", "status": "accepted"}]})
    assert res.status_code == 200, res.text
    assert (tmp_path / "experiments" / "runs" / "img_001.json").exists()
    assert (tmp_path / "dataset" / "processed" / "img_001_D1.jpg").read_bytes() == b"hi"


def test_enhance_by_image_id_and_save(tmp_path, monkeypatch, room):
    import cv2

    from app.config import settings

    (tmp_path / "dataset" / "raw").mkdir(parents=True)
    (tmp_path / "dataset" / "raw" / "labels.csv").write_text("image_id,filename,defects\nimg_001,img_001.jpg,ok\n")
    cv2.imwrite(str(tmp_path / "dataset" / "raw" / "img_001.jpg"), room)
    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    res = client.post("/enhance", json={"image_id": "img_001", "save_as": "img_001_D1", "return_image": False})
    assert res.status_code == 200, res.text
    assert res.json()["image_b64"] is None and res.json()["output_path"] == "dataset/processed/img_001_D1.jpg"
    assert (tmp_path / "dataset" / "processed" / "img_001_D1.jpg").exists()
    assert client.get("/dataset/img_001/file").headers["content-type"] == "image/jpeg"
    assert client.get("/processed/img_001_D1.jpg").status_code == 200
    assert client.post("/enhance", json={}).status_code == 422


def test_choices_summary_and_cards(tmp_path, monkeypatch):
    """The experiment inside the product: a saved run + blind judgements -> the tally."""
    import json

    from app.config import settings

    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    (tmp_path / "dataset" / "raw").mkdir(parents=True)
    (tmp_path / "dataset" / "raw" / "labels.csv").write_text("image_id,filename,defects\nimg_001,img_001.jpg,tilt\n")
    step = {"module": "Raddrizza", "needed": True, "applied": True, "passed": True, "retried": False, "fidelity": None, "params": {}}
    record = {"image_id": "img_001", "source": "batch", "order": ["D2", "D1", "D3"], "judge": [], "variants": [
        {"variant": "D1", "status": "accepted", "defects": ["tilt"], "steps": [step], "cost_usd": 0, "latency_ms": 1000, "fidelity": {"score": 0.99}},
        {"variant": "D2", "status": "accepted", "defects": ["tilt", "noise"], "steps": [step], "cost_usd": 0.004, "latency_ms": 2000, "fidelity": {"score": 0.98}},
        {"variant": "D3", "status": "rejected_fidelity", "defects": [], "steps": [{**step, "applied": False, "passed": False}], "cost_usd": 0.002, "latency_ms": 9000},
    ]}
    assert client.post("/runs/img_001", json=record).status_code == 200
    assert client.get("/runs/nope/cards").status_code == 404
    cards = client.get("/runs/img_001/cards").json()
    assert cards["ready"] and [c["blind_id"] for c in cards["cards"]] == ["V1", "V2", "V3"]
    assert [c["variant"] for c in cards["cards"]] == ["D2", "D1", "D3"]
    post = lambda **j: client.post("/choices", json={"image_id": "img_001", "tester": "T", **j})
    assert post(task="realism", variant="D3", answer="yes").json()["judgments"] == 1
    assert post(task="realism", variant="D2", answer="no").status_code == 200
    assert post(task="quality", variant="D2", answer="4").status_code == 200
    assert post(task="quality", variant="D2", answer="9").status_code == 422
    assert post(task="best", variant="D2", shown=["D1", "D2", "D3"], order=["D2", "D1", "D3"]).status_code == 200
    s = client.get("/summary").json()
    d2 = next(r for r in s["variants"] if r["variant"] == "D2")
    assert s["choices"] == 1 and s["judgments"] == 4 and d2["chosen"] == 1 and d2["shown"] == 1 and d2["mos"] == 4
    assert d2["diagnosis"]["precision"] == 0.5 and d2["diagnosis"]["recall"] == 1.0  # tilt right, noise invented
    assert d2["effective_rate"] == 1.0 and d2["effective_n"] == 1  # rated 4, not altered
    d3 = next(r for r in s["variants"] if r["variant"] == "D3")
    assert d3["gate_rejected_rate"] == 1.0 and d3["alteration_rate"] == 1.0 and d3["effective_rate"] is None
    assert any(e["variant"] == "D3" for e in s["verdict"]["excluded"])
    assert client.get("/study").json()["testers"] == {"T": 4}


def test_prepare_bounds_size_and_measures(room):
    import cv2

    big = cv2.resize(room, (3200, 2400))
    res = client.post("/prepare", json={"image_b64": encode_b64(big)})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["image_id"].startswith("live_") and body["stats"]["width"] == 1600
    assert max(decode_b64(body["image_b64"]).shape[:2]) == 1600


def test_fidelity_by_image_id_and_save(tmp_path, monkeypatch, room):
    import cv2

    from app.config import settings

    (tmp_path / "dataset" / "raw").mkdir(parents=True)
    (tmp_path / "dataset" / "raw" / "labels.csv").write_text("image_id,filename,defects\nimg_001,img_001.jpg,ok\n")
    cv2.imwrite(str(tmp_path / "dataset" / "raw" / "img_001.jpg"), room)
    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    res = client.post("/fidelity", json={"image_id": "img_001", "candidate_b64": encode_b64(room), "save_as": "img_001_C"})
    assert res.status_code == 200 and res.json()["passed"] is True
    assert (tmp_path / "dataset" / "processed" / "img_001_C.jpg").exists()
    assert client.post("/fidelity", json={"image_id": "img_001"}).status_code == 422


def test_max_side_override(room):
    import cv2

    big = cv2.resize(room, (2400, 1800))
    res = client.post("/prepare", json={"image_b64": encode_b64(big), "max_side": 1024})
    assert res.json()["stats"]["width"] == 1024


def test_gate_remote_requires_url(room):
    assert client.post("/gate_remote", json={"original_b64": encode_b64(room)}).status_code == 422


def test_turns_gives_the_four_quarter_turns(room):
    import base64

    import cv2

    b64 = base64.b64encode(cv2.imencode(".jpg", room)[1].tobytes()).decode("ascii")
    res = client.post("/turns", json={"image_b64": b64}).json()
    assert [t["deg"] for t in res["turns"]] == [0, 90, 180, 270]
    sizes = []
    for t in res["turns"]:
        img = cv2.imdecode(__import__("numpy").frombuffer(base64.b64decode(t["image_b64"]), "uint8"), cv2.IMREAD_COLOR)
        sizes.append(img.shape[:2])
    assert max(sizes[0]) <= 512 and sizes[1] == sizes[0][::-1] and sizes[2] == sizes[0]
