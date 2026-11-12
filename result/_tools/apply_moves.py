"""Apply a move plan: [{src, dst, method}] where method in git_mv|mv|copy.

Every action is appended to result/_movelog.tsv (method, src, dst) so the
reorganisation can be undone by replaying the log backwards.
Usage: python apply_moves.py plan.json [--dry-run]
"""
import json, os, shutil, subprocess, sys

ROOT = "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
LOG = os.path.join(ROOT, "result", "_movelog.tsv")


def tracked(path):
    rel = os.path.relpath(path, ROOT)
    out = subprocess.run(["git", "ls-files", "--", rel], cwd=ROOT,
                         capture_output=True, text=True).stdout
    return bool(out.strip())


def main():
    plan = json.load(open(sys.argv[1]))
    dry = "--dry-run" in sys.argv
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    errors = []
    for item in plan:
        src, dst, method = item["src"], item["dst"], item["method"]
        if not os.path.exists(src):
            errors.append(f"missing src {src}")
            continue
        if os.path.exists(dst):
            errors.append(f"dst exists {dst}")
            continue
        if method == "git_mv" and not (src.startswith(ROOT) and tracked(src)):
            method = "mv"
        print(method, src, "->", dst)
        if dry:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if method == "git_mv":
            r = subprocess.run(["git", "mv", os.path.relpath(src, ROOT),
                                os.path.relpath(dst, ROOT)], cwd=ROOT,
                               capture_output=True, text=True)
            if r.returncode:
                errors.append(f"git mv failed {src}: {r.stderr.strip()}")
                continue
        elif method == "mv":
            shutil.move(src, dst)
        elif method == "copy":
            if os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True)
            else:
                shutil.copy2(src, dst)
        with open(LOG, "a") as f:
            f.write(f"{method}\t{src}\t{dst}\n")
    print(f"\n{len(errors)} errors")
    for e in errors:
        print("  ", e)


if __name__ == "__main__":
    main()
