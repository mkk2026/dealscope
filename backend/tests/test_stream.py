import json

from app.pipeline import stream


async def test_replay_yields_events_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "DEMO_DIR", tmp_path)
    events = [
        {"type": "stage", "stage": "collect", "status": "done", "sources": 3, "_t": 0.0},
        {"type": "fact", "claim": "x", "_t": 0.01},
        {"type": "cost", "amd_usd": 0.1, "frontier_usd": 2.0, "savings_x": 20, "_t": 0.02},
        {"type": "done", "_t": 0.03},
    ]
    (tmp_path / "rec.jsonl").write_text("\n".join(json.dumps(e) for e in events))

    out = [e async for e in stream.replay_events("rec.jsonl")]
    assert [e["type"] for e in out] == ["stage", "fact", "cost", "done"]
    assert "_t" not in out[0]                       # timing key stripped before emit
    assert out[2]["savings_x"] == 20


async def test_replay_missing_file_emits_error(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "DEMO_DIR", tmp_path)
    out = [e async for e in stream.replay_events("nope.jsonl")]
    assert out == [{"type": "error", "message": "recording not found: nope.jsonl"}]


async def test_replay_blocks_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "DEMO_DIR", tmp_path)
    # only a basename is ever used, so traversal collapses to a missing file
    out = [e async for e in stream.replay_events("../../etc/passwd")]
    assert out[0]["type"] == "error"
