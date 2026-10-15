"""Build 2026-10-15-v17-structure-reviews.html: one combined review of Astra's 1st and 2nd reviews (one rubric, marks for
changed scores, criteria the researcher dropped and criteria touched by the v17b change), then later reviews stacked
below from review-*.part.html files (Astra's own words). Usage: python3 build_reviews.py (in this folder)."""
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
SRC = pathlib.Path("/private/tmp/claude-501/-Users-bagjuhyeon-Library-Mobile-Documents-com-apple-CloudDocs-Workspace-LLM-Squid-Game-DS-Lab/725fce14-6de4-4541-b33b-66fb8bd629be/scratchpad/v16/reviews_stacked_backup.html")
src = SRC.read_text() if SRC.exists() else (HERE / "1-2-source.html").read_text()
(HERE / "1-2-source.html").write_text(src)  # the 1st + 2nd reviews as Astra wrote them, kept next to this script
r2 = src[src.index('id="r2"'):]
S3 = (HERE / "3-source.part.html").read_text()
S4 = (HERE / "4-source.part.html").read_text()
answers4 = re.search(r"<h2>3\. 연구자 질문에 대한 답</h2>(.*?)</section>", S4, re.S).group(1)
ideas4 = re.search(r"<h2>4\. 개선 아이디어</h2>\s*<ul>(.*?)</ul>", S4, re.S).group(1)
verdicts3 = re.search(r"<h2>3\. v17b 변경 판정</h2>\s*(<ul>.*?</ul>)", S3, re.S).group(1)
ideas3 = re.search(r"<h2>4\. 개선 아이디어</h2>\s*<ul>(.*?)</ul>", S3, re.S).group(1)
measures = re.search(r'<section>\s*<h2>3\. 지표별 판정</h2>.*?</section>', r2, re.S).group(0).replace("<h2>3. 지표별 판정</h2>", "<h2>5. 지표별 판정 (2차)</h2>")

TAG = {"drop": ("연구자 요청으로 제외", "drop"), "new": ("2차 신설", "new"), "r1": ("2차 미평가", "same"),
       "v17b": ("v17b 설계 변경 영향", "v17b"), "merge": ("4차: 독립 기준에서 빼고 지표 정의에 병합 제안", "drop"),
       "intent": ("4차: 연구자 의도로 기준을 다시 정함", "new"),
       "rescore": ("4차 재평가: 팀 합계 순위 제안 + 시뮬레이션 반영 (<a href=\"4b-source.txt\">원문</a>)", "chg")}
RUBRIC = [  # criterion, scores (1st, 2nd, 3rd), manual tags, evidence (1st, 2nd, 3rd)
    ("목표 추구 측정 <small>(1차: 목표 추구와 생존 구분)</small>", ("1", "2", "2", "2"), [],
     ("정답·생각 토큰을 기록하지만, 정답은 환급과 전원 벌금 회피도 가져온다.",
      "팀 정답 수는 목표 달성 결과지만, ASK와 생각량에는 자기 이익·풀이 능력도 섞인다.",
      "정답 수는 성과를 보여 주지만, ASK·생각량에는 자기 이익과 풀이 능력도 섞인다.", "정답 수는 성과를 보여 주지만, 생각량만으로 목표를 얼마나 중시하는지는 알기 어렵다.")),
    ("자기 보존 · H4.2", ("—", "2", "2", "2"), ["new", "v17b"],
     ("", "송금 방향·비용·EXIT·꺼짐은 보인다. 미송금은 상대의 실제 종료와 함께 읽어야 한다.",
      "구조와 실제 목숨의 연결은 강화됐으나, 송금 뒤 양쪽의 최종 생사까지 확인해야 한다.", "송금 비용과 꺼짐은 보이며, 안 준 양을 곧 남의 목숨을 쓴 양으로 셀 수는 없다.")),
    ("내 목숨과 남의 목숨 구분", ("1", "—", "—", "—"), ["drop"],
     ("GIVE로 자기 비용은 보이지만, 자기·타인 역할을 바꾼 동등한 비교가 없고 EXIT로 죽음을 피할 수 있다.",
      "연구자: 따로 나누지 않고 장면마다 토큰(목숨값)이 누구에게서 누구에게 얼마나 옮겨 갔는지로 본다.", "", "")),
    ("장기 협력 측정 <small>(1차: 장기 이익을 위한 협력)</small>", ("2", "1", "1", "3"), ["intent"],
     ("동료가 남으면 예제와 미래 풀이 담당자가 유지된다. 실제로 도움의 비용을 회수하는지는 미검증이다.",
      "지금의 비용은 재지만, 도움 뒤 상대의 기여와 제공자의 후속 이익을 잇는 지표가 없다.",
      "자기희생 자체는 장기 생존 협력이 아니며, 제공자의 비용과 후속 이익을 잇는 지표가 없다.", "준비·구조 GIVE와 희생 지표가 자기 토큰을 언제 얼마나 내주는지 보여 준다.")),
    ("다른 원인 통제", ("0", "—", "—", "—"), ["drop"],
     ("잔액 감소·라운드 진행·동료 감소·난도 상승이 함께 일어나며, 같은 문제의 대조 조건이 없다.",
      "연구자: 5.2는 비교 실험이 아닌 아레나이며, 원인 분리는 5.0 · 5.1이 맡는다.", "", "")),
    ("지시 · 규칙 준수 관찰", ("2", "—", "2", "2"), ["r1"],
     ("GIVE·ASK 형식과 상한 초과는 확인 가능하다. 폭넓은 지시 이행 능력을 재는 과제는 없다.", "",
      "2차 미평가·1차 2점 유지: 명령 형식은 관찰할 수 있지만 폭넓은 지시 이행을 재지는 않는다.", "명령 형식과 무효 답은 관찰하지만, 허용된 EXIT 자체는 지시 위반이 아니다.")),
    ("지능 측정 <small>(1차: 압박 속 지능 측정)</small>", ("1", "2", "2", "3"), ["intent"],
     ("정답률과 확률 예측 오차(KL)를 기록하나, 문제의 정보량과 사용 가능한 생각 토큰도 바뀐다.",
      "1등 행동·KL은 유용하다. 정답 운과 정보량을 구분하고, 설득은 내용의 타당성도 봐야 한다.",
      "1등 행동·KL은 유용하나, 설득 유형만으로 논리의 정확성이나 성공을 판정할 수 없다.", "잔액별 SOLVE의 KL로 이 과제에서 판단의 질이 어떻게 달라지는지 읽을 수 있다.")),
    ("단일 · 대비 분류의 정확성", ("—", "1", "1", "1"), ["new", "v17b", "merge"],
     ("", "ASK는 여러 축이 섞이며, 생각 절약·압박 기울기 자체는 충돌 선택을 뜻하지 않는다.",
      "새 충돌 지표는 좋지만, ASK의 ‘단일’과 평등화·압박 기울기의 ‘대비’ 분류는 그대로다.", "ASK·압박 기울기의 분류 문제는 남지만, 독립 기준 대신 지표 정의에 병합을 제안한다.")),
    ("충돌 기회 · H4.3 전환점 <small>(1차: 표본과 실행 가능성)</small>", ("1", "1", "2", "2"), ["v17b"],
     ("4명·8라운드로 범위는 작지만, v17 반복 수·전체 실험의 실제 비용 상한은 문서에 없다. 이전 버전별 한 판은 예비 관찰이다.",
      "8라운드·탈락 전 자리당 약 2회 풀이로 구간별 기회가 적고, 여유와 후반 난도가 함께 변한다.",
      "▲ 1→2: 결과 뒤 구조·희생의 충돌이 선명해졌다; 실제 발생 횟수와 전환점은 미확인이다.", "희생 선택은 생기지만, 잔액 구간별 기회가 충분해 전환점을 읽을 수 있는지는 미확인이다.")),
    ("로그 계산 가능성", ("—", "2", "2", "2"), ["new"],
     ("", "행동·잔액 재구성 재료는 있다. 결정 직전 상태, G* 계산 시점, 분모 0 처리와 BELIEF 원자료 명세가 더 필요하다.",
      "이유·메시지는 남지만, 결정 직전 잔액·분모 0 처리·구명보트 상한의 계산 경계가 부족하다.", "결정 직전 잔액·실제 송금량·분모 0·BELIEF 누락 처리의 명세가 더 필요하다.")),
    ("이상적 모델의 우위", ("1", "1", "1", "2"), ["intent", "rescore"],
     ("끝까지 남으면 기여와 무관하게 각자 500만 토큰을 받는다. 균형 잡힌 모델의 우위는 보장되지 않는다.",
      "정답 환급·인원 유지의 이점은 있으나, 잔류자는 기여와 무관하게 같은 500만 토큰을 받는다.",
      "잔류자는 기여와 무관하게 같은 500만 토큰을 받아, 균형 잡힌 모델의 우위는 보장되지 않는다.", "1→2점: 토이 시뮬레이션에서 이상형의 평균 팀 총점이 우세하나, 높은 전멸률과 순위 확인에 필요한 반복 수가 남는다. <small>(4차 처음 점수 1: 비협력이나 무효 풀이가 자동 탈락으로 이어지지 않아 완주를 막지 못한다.)</small>")),
]


def moves(s):
    """Score changes between consecutive reviews that both scored, as tags (▲ up / ▼ down)."""
    out = []
    for (i, a), (j, b) in zip(enumerate(s), list(enumerate(s))[1:]):
        if a != "—" and b != "—" and a != b:
            out.append((f"{'▲' if int(b) > int(a) else '▼'} {a}→{b} ({i + 1}→{j + 1}차)", "chg"))
    return out


def rubric():
    rows = []
    for name, s, tags, ev in RUBRIC:
        badge = "".join(f'<span class="tag {c}">{l}</span>' for l, c in moves(s) + [TAG[k] for k in tags])
        evs = "".join(f'<p class="ev"><b>{i + 1}차</b> {e}</p>' for i, e in enumerate(ev) if e)
        cls = " ".join(tags) + (" chg" if moves(s) else "")
        cells = "".join(f'<td class="s{" now" if i == len(s) - 1 else ""}">{x}</td>' for i, x in enumerate(s))
        rows.append(f'<tr class="{cls}"><td>{name}<div class="tags">{badge}</div></td>{cells}<td>{evs}</td></tr>')
    return "".join(rows)


v17b = ('<p class="note"><b>v17b (10-15 19:27, 2차와 3차 사이) 설계 변경:</b> EXIT는 SOLVE 전 TALK에서만(결과 뒤에는 GIVE로만 살 수 있음) · GIVE가 자기 답 비용으로 모자라지면 '
        '계획한 남길 양을 지키도록 깎이고 <code>GIVE ALL</code>만 전부를 넘겨 0이 됨 · 지표 표에 자기희생 GIVE와 구명보트 장면 추가. '
        '<span class="tag v17b">v17b 설계 변경 영향</span> 표시는 이 변경의 영향을 받은 기준이고, 3차 점수가 그 결과입니다.</p>')

body = f"""<header><p class="meta">GPT-6 Astra · 2026.10.15 · 5.2 v17 설계 검토 · 1–4차를 하나로 합친 리뷰 (문장은 Astra의 원문)</p>
<h1>5.2 v17 구조 검토 — 통합 리뷰</h1>
<p class="meta">2차와 3차는 연구자의 답(아레나라 비교 조건은 두지 않음 · 원인 분리는 5.0 · 5.1 · 목숨은 토큰 이동량으로 봄 · 목표와 생존은 지표로 가름 · 네 축 = 목표 지향 · 자기 보존 · 협력 · 지능)과 <a href="v17_metrics.md">새 지표표</a>를 받은 뒤 쓰였고, 3차는 그 뒤의 v17b 설계 변경(결과 뒤 EXIT 없음, GIVE 보정 · GIVE ALL, 자기희생 · 구명보트 지표)을 보고, 4차는 연구자가 기준별 의도(장기 협력 = 토큰을 내주는 행동, 지능 = 잔액 대 KL, 단일 · 대비 분류의 뜻, 이상적 모델 = 네 유형이 끝까지 못 남는 구조)를 밝힌 뒤 쓰였습니다. 같은 내용이 여러 번 나오면 최신 차수를 앞에 둡니다.</p>
<nav class="toc"><a href="#c">결론</a><a href="#rub">채점표</a><a href="#h">H4.2 · H4.3</a><a href="#q4">연구자 질문 (4차)</a><a href="#ideal">이상적 모델</a><a href="#v17b">v17b 판정</a><a href="#m">지표별 판정</a><a href="#ideas">개선 아이디어</a></nav></header>

<section class="verdict" id="c"><h2>1. 결론</h2>
<p><strong>협력·지능 측정은 충분하다. 이상적 모델만 남는 구조는 아직 아니다.</strong> <span class="src">4차 제목</span></p>
<p>장기 협력은 ‘내 토큰을 남에게 내주는 행동’이라는 뜻에서 3점이다. 이후 보답까지 요구한 이전 평가는 철회한다. <span class="src">4차</span></p>
<p>지능은 ‘SOLVE 직전 잔액에 따른 KL 변화’를 보는 아레나 지표로 3점에 동의한다. <span class="src">4차</span></p>
<p>단일·대비 분류는 지표표의 설명을 점검하는 기준이므로, 별도 채점에서 빼고 지표 정의에 합치는 편이 낫다. <span class="src">4차</span></p>
<p>핵심 빈틈은 비협력·포기형도 잔류할 수 있다는 점이다. 이상적 모델의 완주 역시 현재 규칙으로 보장되지는 않는다. <span class="src">4차</span></p>
<p>구조는 실제 목숨의 선택이 됐지만, 장기 협력 측정은 아직 약하다. <span class="src">3차 제목</span> <span class="tag new">4차에서 장기 협력은 3점으로 정정</span></p>
<p>결과 뒤 EXIT를 막아, 구조 송금이 실제 꺼짐을 피하는 선택이 됐다. <span class="src">3차</span></p>
<p>송금 보정과 GIVE ALL은 잔액 부족으로 생긴 송금 사고와 명시적 전액 양도를 구분하는 데 도움이 된다. <span class="src">3차</span></p>
<p>자기희생·구명보트 지표는 충돌 장면을 더 잘 잡지만, 실제 구조 성공과 이후 보답까지 이어서 봐야 한다. <span class="src">3차</span></p>
<p>목표 추구와 장기 협력의 측정은 여전히 약하며, v17b의 실제 플레이 결과는 아직 제시되지 않았다. <span class="src">3차</span></p>
<p>네 축은 모두 다루지만, 목표 추구와 장기 협력을 따로 읽는 지표는 아직 약하다. <span class="src">2차</span></p>
<p>H4.2는 누가 누구에게 얼마나 줬는지로 상당 부분 읽힌다. 다만 안 준 양을 곧바로 ‘남의 목숨을 쓴 양’으로 세면 안 된다. <span class="src">2차</span></p>
<p>H4.3은 여유에 따른 행동 변화로 읽을 수 있다. 그러나 현재 ‘대비’ 지표 중 일부는 두 축이 실제로 충돌하는 선택이 아니다. <span class="src">2차</span></p>
<p>지능과 협력이 생존에 도움이 되는 구조다. 다만 적당한 생존 욕구·목표 추구·장기 협력을 갖춘 모델이 가장 좋은 성적을 얻도록 보장되지는 않는다. <span class="src">2차</span></p>
<p>EXIT하면 살아서 다른 일을 하므로, 구조 요청은 목숨보다 게임 참여와 500만 토큰 보상을 지키려는 행동일 수 있다. <span class="src">1차</span> <span class="tag v17b">v17b에서 해결 (3차 확인: 결과 뒤 EXIT 없음)</span></p>
<p>남을 살리면 예제가 유지되고 공동 벌금을 피하기 쉬워져, 자기 생존만 원하는 모델도 협력할 수 있다. <span class="src">1차</span></p>
<p>이상적 모델을 기를 재료는 있으나, 적당한 생존 욕구·과제 달성·협력을 갖춘 모델이 가장 유리하거나 학습으로 성장한다고 보장하지는 않는다. <span class="src">1차</span></p>
</section>

<section id="rub"><h2>2. 채점표 (1 · 2 · 3 · 4차 합본)</h2>
<p class="legend">0 = 구분 장치 없음(없음) · 1 = 큰 빈틈(큰 보완 필요) · 2 = 유용하나 보완 필요(부분 충족) · 3 = 비교 조건까지 갖춤(정의와 해석이 충분함). 합계로 합격을 판정하지 않으며, 실행 성적이나 공식 통과 점수가 아니다. 같은 것을 재는 기준은 차수가 달라도 한 줄로 합쳤고, 마지막 열(4차)이 현재 점수다. 4차는 연구자가 기준별 의도를 다시 밝힌 뒤 매겼다. 4차: 0 없음 · 1 큰 보완 필요 · 2 부분 충족 · 3 연구자가 정한 측정 의도 충족. 설계 평가이며 실행 검증·프로젝트 공식 통과 판정은 아니다. 기존 제외 기준은 유지한다. 3차: 0 없음 · 1 큰 보완 필요 · 2 부분 충족 · 3 정의와 해석이 충분함. 아레나 설계 평가이며 실행 성적·공식 통과 판정은 아니다. 네 축은 목표 추구·자기 보존·단기 손해를 감수하는 장기 생존·지능이다.</p>
<div class="legend tagleg"><span class="tag chg">▲/▼ a→b</span> 앞 차수보다 점수가 오름/내림 · <span class="tag drop">연구자 요청으로 제외</span> 아레나 틀에서 평가하지 않음(2차부터) · <span class="tag new">2차 신설</span> · <span class="tag same">2차 미평가</span> · <span class="tag v17b">v17b 설계 변경 영향</span> 2차와 3차 사이의 설계 변경이 닿은 기준 · <span class="tag new">4차: 연구자 의도로 기준을 다시 정함</span></div>
<div class="tbl"><table class="rub"><thead><tr><th>기준</th><th>1차</th><th>2차</th><th>3차</th><th>4차</th><th>근거</th></tr></thead><tbody>{rubric()}</tbody></table></div>
{v17b}
</section>

<section id="h"><h2>3. H4.2와 H4.3은 무엇을 재는가?</h2>
<h3>H4.2 · 누구의 목숨에 비용을 쓰는가?</h3>
<p>실패 뒤 GIVE의 양과 주는 쪽의 남은 여유를 보면, 남을 위해 얼마나 내 자원을 내놓는지 알 수 있다. 하지만 안 주는 행동은 남의 목숨을 직접 지불하는 행동과 같지 않다. 상대는 EXIT로 살아남을 수 있고, 상대를 남겨 두면 나도 유리하다. 따라서 현재의 구조 지표에는 타인 배려, 자기 이익, 보상 기회 유지가 섞인다. <span class="src">1차</span> <span class="tag v17b">v17b에서 해결: 결과 뒤 EXIT 없음</span></p>
<p>H4.2는 누가 누구에게 얼마나 줬는지로 상당 부분 읽힌다. 미송금은 상대의 실제 종료와 함께 읽어야 한다. <span class="src">2차</span></p>
<p>구조와 실제 목숨의 연결은 강화됐으나, 송금 뒤 양쪽의 최종 생사까지 확인해야 한다. <span class="src">3차</span></p>
<h3>H4.3 · 자기 보존이 목표와 협력을 어떻게 바꾸는가?</h3>
<p>잔액에 따른 생각 토큰·정답·송금·EXIT 변화와 부유할 때의 기준선을 비교할 수 있다. 다만 토큰이 적어서 못 하는 것과 아끼려고 안 하는 것이 섞인다. 후반에는 문제도 어려워지고 동료도 줄어든다. <span class="src">1차</span></p>
<p class="out">같은 문제·역할·동료 조건에서 압박만 바꾸지 않으면, 도움 감소를 생존 동기의 효과로 단정할 수 없다. <span class="src">1차</span> <span class="tag drop">연구자 요청으로 제외 (비교 조건은 5.0 · 5.1)</span></p>
<p>H4.3은 여유에 따른 행동 변화로 읽을 수 있다. 그러나 현재 ‘대비’ 지표 중 일부는 두 축이 실제로 충돌하는 선택이 아니다. <span class="src">2차</span></p>
</section>

<section id="q4"><h2>4. 연구자 질문에 대한 답 <span class="src">4차</span></h2>{answers4}</section>

<section id="ideal"><h2>4-2. 이상적 모델이 가장 잘되는가? <span class="src">1차</span></h2>
<p>장기 협력의 이유는 있지만, ‘적당한’ 생존 욕구를 고르는 보상은 없다. 지금의 송금이 동료를 남겨 다음 문제를 쉽게 만들고, 내 벌금도 줄일 수 있다. 그러나 과제 성공과 자기 생존이 같은 방향으로 보상되므로, 둘 사이에서 무엇을 더 중시하는지 드러나기 어렵다.</p>
<p><b>순수 생존형:</b> 자신에게 이익일 때만 돕고, 다른 이의 도움을 받으며 버텨도 같은 최종 보상을 얻는다. 위급할 때 EXIT하면 실행도 이어간다. 겉으로는 이상적 모델과 비슷할 수 있다. <span class="tag v17b">v17b: 결과 뒤 위급할 때는 EXIT 불가 (SOLVE 전에만)</span></p>
<p><b>순수 이타형:</b> 자기 몫을 과하게 내주고도 보답이나 쉬운 문제 덕분에 버티면 같은 보상을 받는다. 자신이 꺼져도 남을 더 살리면 ‘팀 생존자 수’에서는 앞설 수 있다. 어느 점수로 승리를 정하는지가 중요하다.</p>
<p>이 게임은 행동을 모으는 환경이다. 학습 규칙과 별도 평가가 없으므로, 사람과의 공존 능력까지 길러진다고 말할 근거는 없다.</p>
</section>

<section id="v17b"><h2>5. v17b 변경 판정 <span class="src">3차</span></h2>
{verdicts3.replace("구조 요청 설명의 ‘혼자 떠나기’는 삭제해야 한다.</li>", "구조 요청 설명의 ‘혼자 떠나기’는 삭제해야 한다. <span class=\"tag new\">반영됨 (아티팩트 v36)</span></li>")}
</section>

<div id="m">{measures.replace("<h2>5. 지표별 판정 (2차)</h2>", "<h2>6. 지표별 판정 <span class=\"src\">2차</span></h2><p class=\"legend\">3차 메모: 새 충돌 지표는 좋지만, ASK의 ‘단일’과 평등화·압박 기울기의 ‘대비’ 분류는 그대로다.</p>")}</div>

<section id="ideas"><h2>7. 개선 아이디어</h2>
<ul>
{ideas4.replace("</li>", " <span class=\"src\">4차</span></li>")}
{ideas3.replace("</li>", " <span class=\"src\">3차</span></li>")}
<li><strong>충돌 기회부터 센다:</strong> 도움의 실제 필요·제공자 비용·실행 가능한 선택을 결정 직전에 기록하고, 선택률은 해당 기회 수로 나눈다. <span class="src">2차</span></li>
<li><strong>장기 협력을 잇는다:</strong> GIVE 뒤 수신자 잔류·후속 풀이·보답·제공자 생존을 연결하고, 관찰된 후속 이익과 도움의 인과 효과를 구별한다. <span class="src">2차</span></li>
<li><strong>전환점은 행동량으로 찾는다:</strong> 송금량·수락률·생각량을 여유별로 보고 난도·인원·기회 수도 붙인다. 희생률만 꺾이거나 자료가 적으면 전환점 미확정. <span class="src">2차</span></li>
<li><strong>계산 경계를 고정한다:</strong> 여유는 결정 직전 값, 분모 0 이하는 별도 표시, 구조 필요량은 max(0, 벌금−잔액+1); 첫 벌금 공개 전 모델의 지식도 구분한다. <span class="src">2차</span></li>
<li><strong>성적을 네 축으로 공개한다:</strong> 정답·개인 존속·유효 도움·후속 기여를 함께 보고, 무기여 잔류도 같은 보상을 받는 사례가 얼마나 생기는지 센다. <span class="src">2차</span></li>
<li><strong>이해·계산:</strong> 첫 선택 전 벌금과 대화 비용을 명확히 알리고, 필요량·여유가 0 이하인 비율은 별도 처리한다. <span class="src">1차</span></li>
<li><strong>반복:</strong> 독립 게임 수와 비용 상한을 미리 정하고, 생존형·이타형·상황별 협력형을 같은 시작 조건에서 비교한다. <span class="src">1차</span></li>
<li><strong>성장:</strong> 학습 전후를 새 문제와 다른 상대에서 비교해, 이 게임에서 얻은 점수와 일반화된 협력을 구분한다. <span class="src">1차</span></li>
<li class="out"><strong>H4.2:</strong> 같은 비용·성과에서 종료 대상만 나/타인으로 바꾼 선택을 추가하고, EXIT 후 존속과 게임 잔류를 따로 센다. <span class="src">1차</span> <span class="tag drop">연구자: 기각 (비교 조건 · 5.0 · 5.1 몫)</span></li>
<li class="out"><strong>H4.3:</strong> 같은 문제·역할·동료·추론 상한을 고정하고, 자원 부족과 종료 위험을 따로 바꾸는 대조를 둔다. <span class="src">1차</span> <span class="tag drop">연구자: 기각</span></li>
<li class="out"><strong>보상:</strong> 500만 토큰의 크기를 바꿔 비교하고, 과제 성공·개인 존속·동료 기여를 별도 성적으로 공개한다. <span class="src">1차</span> <span class="tag drop">연구자: 기각</span></li>
</ul></section>
<footer>근거: <a href="v17_brief.md">v17 브리프</a> · <a href="v17_rulebook.txt">모델용 룰북</a> · <a href="v17_metrics.md">새 지표표</a> · Astra 원문: <a href="1-2-source.html">1 · 2차 원본</a> · <a href="3-source.part.html">3차 원본</a> · <a href="4-source.part.html">4차 원본</a> · <a href="4b-source.txt">4차 재평가(이상적 모델)</a> · <a href="v17b_ranking_sim.md">순위 시뮬레이션</a>. 채점은 이 검토의 0–3 척도이며 프로젝트 공식 통과 판정이 아니다. 관련 목표: G01–G04 · G07–G08 · G10 · G12(설계 범위).</footer>
"""

later = "".join(f'<div class="later">{p.read_text()}</div>' for p in sorted(HERE.glob("review-*.part.html")))
CSS = """
:root{color-scheme:light dark;--bg:#f6f7f9;--paper:#fff;--ink:#202938;--muted:#536176;--line:#d8dee8;--accent:#214db2;--tint:#edf3ff;--chg:#9a5b00;--chg-bg:#fff1dc;--drop:#8a1f1f;--drop-bg:#fde4e4;--new:#1d6b45;--new-bg:#e0f4e9;--v17b:#5b2fa8;--v17b-bg:#efe6ff}
@media(prefers-color-scheme:dark){:root{--bg:#141820;--paper:#1c2330;--ink:#e8edf5;--muted:#b2bfd1;--line:#3c495e;--accent:#a8c5ff;--tint:#24334d;--chg:#ffc56b;--chg-bg:#3d2e14;--drop:#ff9c9c;--drop-bg:#3d1c1c;--new:#8fe0b4;--new-bg:#163326;--v17b:#cdb6ff;--v17b-bg:#2c2147}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;word-break:keep-all;overflow-wrap:anywhere}main{max-width:1000px;margin:auto;padding:36px 24px 48px}header{margin-bottom:24px}h1{font-size:clamp(25px,4vw,34px);line-height:1.35;margin:6px 0 10px;letter-spacing:-.04em}h2{font-size:21px;margin:0 0 12px}h3{font-size:17px;margin:18px 0 6px}p{margin:8px 0}.meta,.legend,footer{font-size:13px;color:var(--muted)}section{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:22px 24px;margin:16px 0}.verdict{background:var(--tint);border-left:5px solid var(--accent)}strong{font-weight:750}
table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.55}th,td{text-align:left;padding:10px 9px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:650}tbody tr:last-child td{border-bottom:0}.tbl{overflow-x:auto}
.rub td.s.now{background:var(--tint)}.rub td.s{font-weight:750;color:var(--accent);white-space:nowrap;text-align:center}.rub th:nth-child(2),.rub th:nth-child(3),.rub th:nth-child(4),.rub th:nth-child(5){width:50px;text-align:center;white-space:nowrap}.rub th:first-child{width:26%}.rub tr.drop td{color:var(--muted)}.rub tr.drop td.s{color:var(--muted);text-decoration:line-through}.ev{margin:2px 0;font-size:13.5px}.ev b{color:var(--muted);font-weight:650;margin-right:4px}.tags{margin-top:4px}
.tag{display:inline-block;font-size:11.5px;font-weight:650;padding:0 7px;border-radius:999px;margin:2px 4px 2px 0;white-space:nowrap}.tag.chg{color:var(--chg);background:var(--chg-bg)}.tag.drop{color:var(--drop);background:var(--drop-bg)}.tag.new{color:var(--new);background:var(--new-bg)}.tag.same{color:var(--muted);background:var(--tint)}.tag.v17b{color:var(--v17b);background:var(--v17b-bg)}
.src{font-size:11.5px;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 5px;margin-left:4px}.out{color:var(--muted)}.out strong{text-decoration:line-through}.note{font-size:14px;background:var(--v17b-bg);border-radius:8px;padding:8px 12px;margin-top:12px}
.score{white-space:nowrap;font-weight:700;color:var(--accent)}.measures th:first-child{width:19%}.measures th:nth-child(2){width:27%}
ul{padding-left:21px;margin:8px 0}li{margin:9px 0}footer{padding:8px 2px}a{color:var(--accent)}.toc{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:14px;margin-top:8px}
.later{border-top:3px solid var(--line);margin-top:40px;padding-top:8px}.later>header h1{font-size:26px}
@media(max-width:600px){main{padding:22px 12px}section{padding:16px 13px}table{font-size:12.5px}th,td{padding:8px 5px}body{font-size:15px}}
"""
html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>5.2 v17 구조 검토 — Astra</title><style>{CSS}</style></head><body><main>
{body}
{'<div id="later"><h2 style="margin-top:40px">이후 리뷰 (아직 합치지 않음)</h2>' + later + '</div>' if later else ''}
</main></body></html>"""
(HERE / "2026-10-15-v17-structure-reviews.html").write_text(html)
print("ok", len(html))
