from __future__ import annotations

from pathlib import Path
import argparse
import sys

from crowd_monitor.team_b import TeamBValidationError, parse_and_validate_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one JSON payload against the strict Team B contract."
    )
    parser.add_argument("message_type", choices=["people_flow", "event"])
    parser.add_argument(
        "path",
        nargs="?",
        help="JSON file to validate; omit it to read JSON from standard input.",
    )
    args = parser.parse_args()

    raw = Path(args.path).read_text(encoding="utf-8") if args.path else sys.stdin.read()
    try:
        parse_and_validate_json(raw, args.message_type)
    except TeamBValidationError as exc:
        for error in exc.errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print(f"VALID: {args.message_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
