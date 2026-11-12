from pathlib import Path
from html import escape
import json
import subprocess

root=Path(__file__).resolve().parents[2]
rows=json.loads((root/'configs/hermes-bots/roster.json').read_text())['bots']
by_id={r['id']:r for r in rows}
parts=['''<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1140" viewBox="0 0 1440 1140" role="img" aria-labelledby="title desc">
<title id="title">LLM Squid Game — Specialist Bot Team</title>
<desc id="desc">Nine bots: Director coordinates research, beta testing, implementation, independent verification, and operation. Phase two training bots are deferred.</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#77859a"/></marker></defs>
<rect width="1440" height="1140" fill="#f7f9fc"/>
<g font-family="Apple SD Gothic Neo, Arial, sans-serif" fill="#17243b">
<text x="60" y="60" font-size="18" fill="#526581">LLM SQUID GAME / PHASE 1</text>
<text x="60" y="110" font-size="38" font-weight="700">연구 · 게임 · 검증을 잇는 9개 봇</text>
<text x="60" y="146" font-size="19" fill="#526581">설계와 타당성 검토, 구현과 독립 검증을 분리합니다.</text>
''']
def path(d,dash=False):
    parts.append(f'<path d="{d}" fill="none" stroke="#77859a" stroke-width="2" marker-end="url(#arrow)"'+(' stroke-dasharray="7 5"' if dash else '')+'/>')
def card(name,x,y,w,fill='#fff',accent='#3c75bc'):
    r=by_id[name]
    title='Beta Tester' if name=='beta-tester' else r['title']
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="110" rx="14" fill="{fill}" stroke="#d6deea"/><rect x="{x}" y="{y+18}" width="5" height="74" rx="2" fill="{accent}"/>')
    for yy,size,weight,text,color in [(y+32,23,700,title,'#17243b'),(y+62,18,400,r['role'],'#465871'),(y+89,14,400,'@'+name,'#63758d')]:
        parts.append(f'<text x="{x+25}" y="{yy}" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(text)}</text>')
card('arena-director',445,180,550,'#eaf0fb')
parts.append('<text x="80" y="352" font-size="23" font-weight="700">연구 · 설계 · 상황 인지</text><text x="850" y="352" font-size="23" font-weight="700">구현 · 검증 · 운영</text>')
path('M 600 290 V 317 H 42 V 956')
path('M 840 290 V 318 H 1100 V 380')
for idx,name in enumerate(['game-designer','construct-auditor','social-dynamics','metric-analyst','beta-tester']):
    y=380+130*idx
    path(f'M 42 {y+55} H 80')
    card(name,80,y,610,'#fff4de' if name=='beta-tester' else '#fff','#c88b21' if name=='beta-tester' else '#3c75bc')
for idx,name in enumerate(['arena-engineer','arena-verifier','arena-operator']):
    y=380+155*idx
    card(name,850,y,510,'#fff','#269278')
    if idx<2: path(f'M 1100 {y+110} V {y+155}')
path('M 1360 752 H 1395 V 235 H 995',True)
parts.append('<text x="1250" y="270" font-size="15" fill="#526581">실행 근거</text>')
path('M 690 955 H 723 V 825 H 690',True)
parts.append('<text x="750" y="921" font-size="18" font-weight="700">상황 인지 베타테스트</text><text x="750" y="953" font-size="18" fill="#526581">상태 이해 / 평가 인지 / 행동 변화</text><text x="750" y="982" font-size="16" fill="#526581">평가 언급만으로 기만·의식을 판정하지 않음</text>')
parts.append('<path d="M 60 1050 H 1380" stroke="#d6deea"/><text x="60" y="1083" font-size="17" fill="#526581">공통 기준: 규칙·코드 버전 / 성공 기준 / 예산 / 실제 실행 근거 / 다음 담당자</text><text x="60" y="1113" font-size="16" fill="#526581">Phase 2 (추후): Trajectory Curator · Learning Scientist     |     정기 실행·게임 실험은 아직 시작하지 않음</text></g></svg>')
dest=root/'docs/agents/structure.svg'
dest.write_text(''.join(parts))
subprocess.run(['rsvg-convert',str(dest),'-o',str(dest.with_suffix('.png'))],check=True)
print('SVG and PNG rendered from verified roster; Mermaid retained as editable relationship source.')
