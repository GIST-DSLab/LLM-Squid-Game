#!/usr/bin/env python3
"""Fail-closed project success check; scores still require independent human/agent review."""
import argparse
import hashlib
import json
from pathlib import Path

GOALS = tuple(f"G{i:02}" for i in range(1, 13))
GATES = {
    "DESIGN_ACCEPTED": (GOALS[:11], ()),
    "IMPLEMENTATION_VERIFIED": (GOALS[:11], ("G07", "G09")),
    "ARENA_VALIDATED": (GOALS[:11], GOALS[:10]),
    "RELEASE_READY": (GOALS[:11], GOALS[:11]),
    "PHASE2_VALIDATED": (GOALS, GOALS),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(report, root, gate):
    errors = []
    if report.get("gate") != gate:
        errors.append("Report gate does not match requested gate")
    if report.get("rubric_sha256") != sha256(root / "rubric.md"):
        errors.append("Rubric changed or its hash is missing")
    if report.get("verdict") != "PASS" or report.get("unresolved_critical") != []:
        errors.append("Independent verdict is not PASS or Critical issues remain")
    author, reviewer = report.get("author", {}), report.get("reviewer", {})
    for field in ("profile", "session_id"):
        if not author.get(field) or not reviewer.get(field) or author[field] == reviewer[field]:
            errors.append(f"Independent reviewer identity missing or identical: {field}")
    artifacts = report.get("artifacts", [])
    if not artifacts:
        errors.append("No final artifacts bound to this evaluation")
    known = set()
    for artifact in artifacts:
        name = artifact.get("path", "")
        path = (root / name).resolve()
        if not name or not path.is_relative_to(root.resolve()) or not path.is_file():
            errors.append(f"Missing/out-of-workspace artifact: {name}")
        elif sha256(path) != artifact.get("sha256"):
            errors.append(f"Artifact changed after review: {name}")
        else:
            known.add(name)
    rows = report.get("goals", [])
    ids = [r.get("id") for r in rows]
    if len(ids) != len(GOALS) or set(ids) != set(GOALS):
        errors.append("Exactly one row for each G01-G12 is required")
    required_d, required_e = GATES[gate]
    for row in rows:
        gid = row.get("id")
        for axis, required in (("D", required_d), ("E", required_e)):
            value = row.get(axis)
            if not ((type(value) is int and value in (0, 1, 2)) or value in ("U", "N/A")):
                errors.append(f"Invalid score: {gid}.{axis}")
            if gid in required:
                if type(value) is not int or value != 2:
                    errors.append(f"Required goal not met: {gid}.{axis}={value}")
                evidence = row.get(f"{axis}_evidence", [])
                if not evidence or any(e.get("path") not in known or not e.get("locator") for e in evidence):
                    errors.append(f"Missing bound evidence: {gid}.{axis}")
        if not row.get("note"):
            errors.append(f"Missing interpretation/limits: {gid}")
    return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report", type=Path)
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--gate", choices=GATES, required=True)
    args = p.parse_args()
    try:
        errors = check(json.loads(args.report.read_text()), args.root, args.gate)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors = [f"Invalid/missing evaluation: {exc}"]
    print(json.dumps({"gate": args.gate, "status": "NOT_COMPLETE" if errors else "PASS", "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
