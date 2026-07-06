"""Verify audit log hash-chain integrity.

Usage:
    docker exec wmcp python src/audit_verify.py
    docker exec wmcp python src/audit_verify.py --log /app/data/audit.log
    docker exec wmcp python src/audit_verify.py --log /app/data/audit.log --seed <hex>

Exit codes: 0 = PASS, 1 = chain broken or file error.

--seed is needed for rotated log segments that continue from a previous file.
The seed value is the SHA-256 of the last line of the previous segment
(visible as the "prev" field of the first entry in the current file).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

GENESIS = "0" * 64


def verify(log_path: str, seed: str = GENESIS) -> bool:
    path = Path(log_path)
    if not path.exists():
        print(f"[audit_verify] File not found: {log_path}", file=sys.stderr)
        return False

    prev_hash = seed
    entry_count = 0
    error_count = 0

    with path.open(encoding="utf-8", errors="replace") as f:
        for raw_lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue

            entry_count += 1

            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[FAIL] line {raw_lineno}: invalid JSON — {exc}")
                error_count += 1
                # Advance hash so subsequent failures are reported independently
                prev_hash = hashlib.sha256(line.encode()).hexdigest()
                continue

            claimed = entry.get("prev")
            if claimed != prev_hash:
                print(
                    f"[FAIL] line {raw_lineno} (entry {entry_count}): prev_hash mismatch\n"
                    f"  expected : {prev_hash}\n"
                    f"  got      : {claimed}\n"
                    f"  ts       : {entry.get('ts', '?')}  action: {entry.get('action', '?')}"
                )
                error_count += 1

            prev_hash = hashlib.sha256(line.encode()).hexdigest()

    if entry_count == 0:
        print("[audit_verify] Log is empty — nothing to verify")
        return True

    if error_count == 0:
        print(f"[PASS] Chain intact — {entry_count} entries verified ({log_path})")
        return True

    print(f"[FAIL] {error_count} integrity error(s) in {entry_count} entries ({log_path})")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify wago-plc audit log hash chain")
    parser.add_argument("--log", default="/app/data/audit.log", help="Path to audit log file")
    parser.add_argument(
        "--seed",
        default=GENESIS,
        metavar="HEX",
        help="Starting prev_hash (64 hex chars). Use for rotated log segments.",
    )
    args = parser.parse_args()

    if args.seed != GENESIS and len(args.seed) != 64:
        print(f"[audit_verify] --seed must be 64 hex characters, got {len(args.seed)}", file=sys.stderr)
        sys.exit(1)

    ok = verify(args.log, seed=args.seed)
    sys.exit(0 if ok else 1)
