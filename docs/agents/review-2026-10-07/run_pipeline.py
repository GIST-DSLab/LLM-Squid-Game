"""Bounded native Hermes profile calls; the coordinator alone saves artifacts."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
WORKTREE = ROOT.parents[2]
MODELS = {
    'construct-auditor': ('gpt-6-astra', 'high'),
    'beta-tester': ('gpt-6-astra', 'high'),
    'arena-operator': ('gpt-6-luna', 'max'),
}


def run(stage, role):
    model, effort = MODELS.get(role, ('gpt-6.1-sol', 'high'))
    command = [str(Path.home() / '.local/bin/hermes'), '-p', role, 'chat', '--in', str(WORKTREE),
               '--query-file', str(ROOT / 'prompts' / f'{stage}.md'), '--model', model,
               '--provider', 'openai-codex', '--reasoning', effort, '--max-turns', '3',
               '--run-budget', '240', '--format', 'stream-json']
    env = dict(os.environ)
    env['PATH'] = str(Path.home() / '.local/bin') + os.pathsep + env.get('PATH', '')
    started = time.monotonic()
    with (ROOT / 'runs' / f'{stage}.jsonl').open('w') as out, (ROOT / 'runs' / f'{stage}.stderr').open('w') as err:
        try:
            code = subprocess.run(command, cwd=WORKTREE, env=env, stdout=out, stderr=err, timeout=300).returncode
        except subprocess.TimeoutExpired:
            code = 124
    records = []
    for line in (ROOT / 'runs' / f'{stage}.jsonl').read_text().splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    init = next((x for x in records if x.get('type') == 'system' and x.get('subtype') == 'init'), {})
    final = next((x for x in reversed(records) if x.get('type') == 'result'), {})
    text = final.get('text', '')
    success = code == 0 and final.get('exit_code') == 0 and bool(text.strip())
    receipt = {'stage': stage, 'profile': role, 'requested_model': model, 'reported_model': init.get('model'),
               'effort': effort, 'session_id': final.get('session_id', init.get('session_id')),
               'exit_code': code, 'result_exit_code': final.get('exit_code'), 'response_returned': success,
               'seconds': time.monotonic() - started, 'tokens': final.get('tokens'),
               'status': 'returned-awaiting-review' if success else 'failed'}
    (ROOT / 'runs' / f'{stage}.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    if success:
        (ROOT / f'{stage}.md').write_text(text + '\n')
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    return success


if __name__ == '__main__':
    tasks = [tuple(arg.split(':', 1)) for arg in sys.argv[1:]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(lambda task: run(*task), tasks))
    raise SystemExit(0 if all(outcomes) else 1)
