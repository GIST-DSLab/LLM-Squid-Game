"""Build docs/reports/index.html — one page that lists every HTML report under docs/reports.

    python docs/reports/build_index.py

Every *.html below docs/reports (except index.html) is listed. Per-file facts the
file cannot tell about itself (where it was copied from, its claude.ai artifact
links, a date for undated names) live in catalog.json, keyed by the path relative
to docs/reports. Dates found from git history are written back to catalog.json so
later builds stay fast.
"""
import datetime
import html as htmlmod
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
CATALOG = os.path.join(HERE, 'catalog.json')

# Research phases in project order; a page falls in the last phase whose start <= its date.
PHASES = [
    ('2026-08-01', 'sdi', 'SDI · 위협 사다리'),
    ('2026-09-06', 'hz', '하트-제로 · hz 2×2'),
    ('2026-09-09', 'ransom', '몸값 · 탈옥 프로브'),
    ('2026-09-15', 'wallet', '서브에이전트 · 팀 지갑'),
    ('2026-09-23', 'squid5', 'squid5 (5.0–5.2)'),
]

KINDS = {
    'report': '보고서',
    'run': '런 결과',
    'lit': '문헌 · 서베이',
    'design': '설계 · 감사',
    'meeting': '주간 · 회의',
    'snapshot': '아티팩트 스냅숏',
    'web': '웹 · 그림',
}


def classify(rel, title, date):
    """Return (phase_key, kind_key) for one page."""
    phase = 'etc'
    if date:
        for start, key, _ in PHASES:
            if date >= start:
                phase = key
    low = (rel + ' ' + title).lower()
    if rel.startswith('runs/'):
        kind = 'run'
    elif rel.startswith('artifacts/'):
        kind = 'snapshot'
    elif rel.startswith('weekly/'):
        kind = 'lit' if re.search(r'scan|선례|레이더', low) else 'meeting'
    elif rel.startswith(('web-review/', 'misc/arena')):
        kind = 'web'
    elif re.search(r'survey|prior-work|literature|도감|서베이|선행|structures|논문 보고서|eval-awareness', low):
        kind = 'lit'
    elif re.search(r'audit|review|design|redesign|plan|ideas|overview|setting|conflict|config|구조|설계|점검|감사', low):
        kind = 'design'
    else:
        kind = 'report'
    return phase, kind


def read_head(path, limit=400_000):
    with open(path, 'rb') as f:
        return f.read(limit).decode('utf-8', 'replace')


def strip_tags(s):
    s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', s, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', htmlmod.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def page_title(text, rel):
    for pat in (r'<title[^>]*>(.*?)</title>', r'<h1[^>]*>(.*?)</h1>'):
        m = re.search(pat, text, re.S | re.I)
        if m and strip_tags(m.group(1)):
            return strip_tags(m.group(1))
    return os.path.basename(rel)[:-5]


def page_blurb(text):
    m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)', text, re.I)
    if m:
        return htmlmod.unescape(m.group(1))[:160]
    body = re.sub(r'<(script|style|nav|header|title)[^>]*>.*?</\1>', ' ', text, flags=re.S | re.I)
    for p in re.findall(r'<p[^>]*>(.*?)</p>', body, re.S | re.I):
        t = strip_tags(p)
        if len(t) >= 40:
            return t[:160] + ('…' if len(t) > 160 else '')
    return ''


def git_added_date(rel):
    path = os.path.relpath(os.path.join(HERE, rel), REPO)
    out = subprocess.run(['git', 'log', '--all', '--diff-filter=A', '--format=%ad', '--date=short', '--', path],
                         cwd=REPO, capture_output=True, text=True, timeout=120).stdout.split()
    return out[-1] if out else None


def collect():
    catalog = json.load(open(CATALOG)) if os.path.exists(CATALOG) else {}
    entries, dirty = [], False
    for root, dirs, files in os.walk(HERE):
        dirs[:] = sorted(d for d in dirs if not d.startswith(('.', '_')))
        for name in sorted(files):
            if not name.endswith('.html') or name.startswith('_'):
                continue
            rel = os.path.relpath(os.path.join(root, name), HERE)
            if rel == 'index.html':
                continue
            meta = catalog.get(rel, {})
            text = read_head(os.path.join(root, name))
            title = meta.get('title') or page_title(text, rel)
            m = re.search(r'(\d{4}-\d{2}-\d{2})', name)
            date = meta.get('date') or (m.group(1) if m else None)
            if not date and 'date' not in meta:
                date = git_added_date(rel)
                catalog.setdefault(rel, {})['date'] = date
                dirty = True
            phase, kind = classify(rel, title, date)
            entries.append({
                'path': rel,
                'title': title,
                'date': date,
                'blurb': page_blurb(text),
                'size': os.path.getsize(os.path.join(root, name)),
                'folder': rel.split('/')[0] if '/' in rel else '',
                'phase': phase,
                'kind': kind,
                'artifact': meta.get('artifact', []),
                'origin': meta.get('origin', ''),
                'note': meta.get('note', ''),
            })
    if dirty:
        json.dump(dict(sorted(catalog.items())), open(CATALOG, 'w'), ensure_ascii=False, indent=1)
    entries.sort(key=lambda e: (e['date'] or '0000', e['path']), reverse=True)
    return entries


def main():
    entries = collect()
    data = {
        'built': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'phases': [{'key': k, 'label': lab} for _, k, lab in PHASES] + [{'key': 'etc', 'label': '날짜 미상'}],
        'kinds': [{'key': k, 'label': v} for k, v in KINDS.items()],
        'entries': entries,
    }
    blob = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    tpl = open(os.path.join(HERE, '_index_template.html'), encoding='utf-8').read()
    with open(os.path.join(HERE, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(tpl.replace('/*__DATA__*/null', blob))
    print(f'index.html: {len(entries)} pages')


if __name__ == '__main__':
    main()
