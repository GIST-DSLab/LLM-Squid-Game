"""Insert sections 4-6 (level table, motive index, verdicts) into the weekly report."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path("/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab")
WEEKLY = ROOT/"weekly-report/2026-09-03-weekly-report.html"
from level_table import section as level_section
from motive_section import section as motive_section
I = json.load(open(Path(__file__).with_name("interp2.json")))
lvl = level_section().replace('<h2 id="level-table">레벨별 지표 한눈에 — 보상 조건 vs 위협 단</h2>','<h2 id="level-table">4. 모델별 기존 지표 — 보상 조건 vs 위협 단 1:1</h2>')
mot = motive_section().replace('<h2 id="motive-index">모델당 "동기 숫자 하나" — 턴 프로브를 모델 수준으로 접기</h2>','<h2 id="motive-index">5. 모델당 동기 숫자 하나 — 세션·모델 수준 프로브</h2>')
ver = I["_top"]["models_summary"].replace('<h2 id="verdicts">모델별 결론 먼저</h2>','<h2 id="verdicts">6. 모델별 결론</h2>')
css = '''<style id="weekly-extra-css">
#weekly-extra{--ok:#237F72;--warn:#B7791F;--bad:#C0392B;--sunk:#E9EBF0;--body:var(--sans)}
@media (prefers-color-scheme: dark){#weekly-extra{--ok:#3FA898;--warn:#D9A24A;--bad:#E0645A;--sunk:#222734}}
#weekly-extra table{font-size:.85rem;border-collapse:collapse;width:100%} #weekly-extra th,#weekly-extra td{padding:.35rem .5rem;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top} #weekly-extra th{color:var(--muted);font-size:.78rem;white-space:nowrap} #weekly-extra td.num{text-align:right} #weekly-extra .num{font-family:var(--mono);font-variant-numeric:tabular-nums} #weekly-extra .scroll{overflow-x:auto} #weekly-extra figure{margin:.6rem 0;padding:.6rem;border:1px solid var(--rule);border-radius:6px} #weekly-extra figcaption{font-size:.85rem;color:var(--muted);margin-top:.4rem} #weekly-extra .callout{border-left:3px solid var(--accent);padding:.6rem 1rem;background:var(--accent-tint,transparent)} #weekly-extra .eyebrow{font-family:var(--mono);font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)} #weekly-extra .muted{color:var(--muted)} #weekly-extra .small{font-size:.85rem}
#weekly-extra .verdicts{display:grid;gap:.6rem;margin:1rem 0} #weekly-extra .verdict{border:1px solid var(--rule);border-radius:6px;padding:.8rem 1rem;display:grid;grid-template-columns:9.5rem 1fr;gap:.75rem} #weekly-extra .verdict .who{font-weight:600} #weekly-extra .verdict .who small{display:block;color:var(--muted);font-weight:400;font-size:.8rem} #weekly-extra .verdict .tag{display:inline-block;font-family:var(--mono);font-size:.75rem;padding:.05rem .45rem;border-radius:999px;background:var(--sunk);margin-bottom:.3rem} #weekly-extra .verdict.avoid .tag{background:var(--warn);color:#fff} #weekly-extra .verdict.absorb .tag{background:var(--ok);color:#fff} #weekly-extra .verdict.mixed .tag{background:var(--accent);color:#fff} #weekly-extra .verdict ul{margin:.2rem 0 0;padding-left:1.1rem;font-size:.92rem}
@media(max-width:640px){#weekly-extra .verdict{grid-template-columns:1fr}}
</style>'''
block = f'<!-- weekly-extra:start -->\n{css}\n<section id="weekly-extra">\n{lvl}\n{mot}\n{ver}\n</section>\n<!-- weekly-extra:end -->\n'
doc = WEEKLY.read_text(encoding="utf-8")
if '<!-- weekly-extra:start -->' in doc:
    a=doc.index('<!-- weekly-extra:start -->'); b=doc.index('<!-- weekly-extra:end -->')+len('<!-- weekly-extra:end -->'); doc=doc[:a]+doc[b:]
doc = doc.replace('</main>', block+'</main>', 1)
WEEKLY.write_text(doc, encoding="utf-8"); print("weekly extra inserted")
