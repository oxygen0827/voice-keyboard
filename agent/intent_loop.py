"""One-command intent training loop helpers."""

from __future__ import annotations

from pathlib import Path

from agent.intent_evaluation import evaluate_reviewed_samples
from agent.intent_sync import sync_corrected_intents


def run_training_loop(
    *,
    sample_path: Path | str,
    server: str,
    token: str = "",
    override_path: Path | str,
    source: str = "",
    limit: int = 1000,
    http,
) -> dict:
    headers = {"Content-Type": "application/jsonl"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = Path(sample_path).expanduser().read_text(encoding="utf-8")
    upload_response = http.post(
        server.rstrip("/") + "/v1/intent-samples/batches",
        params={"source": source},
        data=body.encode("utf-8"),
        headers=headers,
        timeout=30,
    )
    upload_response.raise_for_status()

    sync_headers = {}
    if token:
        sync_headers["Authorization"] = f"Bearer {token}"
    corrections_response = http.get(
        server.rstrip("/") + "/v1/intent-samples/corrections",
        params={"limit": limit},
        headers=sync_headers,
        timeout=30,
    )
    corrections_response.raise_for_status()
    rows = corrections_response.json().get("items", [])
    sync = sync_corrected_intents(rows, override_path=override_path)
    evaluation = evaluate_reviewed_samples(sample_path, override_path=override_path)
    return {
        "upload": upload_response.json(),
        "sync": sync,
        "evaluation": evaluation,
    }
