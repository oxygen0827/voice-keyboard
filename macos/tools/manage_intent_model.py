"""Manage local intent model versions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.intent_model import (
    activate_intent_model_version,
    list_intent_model_versions,
    pull_published_intent_model,
    rollback_intent_model,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Voice Keyboard local intent model versions")
    parser.add_argument(
        "--registry-dir",
        default=str(Path.home() / ".voice-keyboard" / "intent_models"),
        help="model registry dir",
    )
    parser.add_argument("--json", action="store_true", help="print JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="list model versions")
    list_parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    activate = subparsers.add_parser("activate", help="activate a model version")
    activate.add_argument("version")
    activate.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    rollback = subparsers.add_parser("rollback", help="activate the previous model version")
    rollback.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    pull = subparsers.add_parser("pull-published", help="pull and activate the server published model")
    pull.add_argument(
        "--server",
        default=os.getenv("INTENT_TRAINING_SERVER", "http://127.0.0.1:8000"),
        help="training server base URL",
    )
    pull.add_argument(
        "--token",
        default=os.getenv("INTENT_TRAINING_UPLOAD_TOKEN", ""),
        help="server token",
    )
    pull.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.command == "list":
        result = {"versions": list_intent_model_versions(args.registry_dir)}
    elif args.command == "activate":
        result = activate_intent_model_version(args.registry_dir, args.version)
    elif args.command == "rollback":
        result = rollback_intent_model(args.registry_dir)
    else:
        result = pull_published_intent_model(
            args.server,
            args.registry_dir,
            token=args.token,
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "list":
        for item in result["versions"]:
            marker = "*" if item["current"] else " "
            print(f"{marker} {item['version']} examples={item['examples']} path={item['path']}")
    elif args.command in {"activate", "rollback"}:
        print(
            f"current={result['current']} version={result['version']} "
            f"previous={result['previous_version']}"
        )
    else:
        print(
            f"current={result['current']} version={result['version']} "
            f"previous={result['previous_version']} examples={result['examples']}"
        )


if __name__ == "__main__":
    main()
