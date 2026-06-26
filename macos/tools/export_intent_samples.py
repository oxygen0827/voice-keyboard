"""Export local intent-training samples.

Examples:
  python tools/export_intent_samples.py --format jsonl
  python tools/export_intent_samples.py --format csv --output intent_samples.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.intent_training import export_samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Voice Keyboard intent samples")
    parser.add_argument(
        "--input",
        default=str(Path.home() / ".voice-keyboard" / "intent_samples.jsonl"),
        help="source JSONL file",
    )
    parser.add_argument("--output", default=None, help="target file")
    parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    args = parser.parse_args()

    path = export_samples(args.input, args.output, fmt=args.format)
    print(path)


if __name__ == "__main__":
    main()
