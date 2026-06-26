"""Upload local intent-training samples to a review server."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload Voice Keyboard intent samples")
    parser.add_argument(
        "--input",
        default=str(Path.home() / ".voice-keyboard" / "intent_samples.jsonl"),
        help="source JSONL file",
    )
    parser.add_argument(
        "--server",
        default=os.getenv("INTENT_TRAINING_SERVER", "http://127.0.0.1:8000"),
        help="training server base URL",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("INTENT_TRAINING_UPLOAD_TOKEN", ""),
        help="upload token",
    )
    parser.add_argument("--source", default="", help="source label for this upload batch")
    parser.add_argument("--dry-run", action="store_true", help="print row count without uploading")
    args = parser.parse_args()

    path = Path(args.input).expanduser()
    if not path.exists():
        raise SystemExit(f"input file not found: {path}")
    body = path.read_text(encoding="utf-8")
    rows = [line for line in body.splitlines() if line.strip()]
    if args.dry_run:
        print(f"rows={len(rows)}")
        return

    url = args.server.rstrip("/") + "/v1/intent-samples/batches"
    headers = {"Content-Type": "application/jsonl"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    response = requests.post(
        url,
        params={"source": args.source},
        data=body.encode("utf-8"),
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    print(response.text)


if __name__ == "__main__":
    main()
