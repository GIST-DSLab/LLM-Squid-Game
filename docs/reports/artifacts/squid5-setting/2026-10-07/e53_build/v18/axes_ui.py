"""v18 graphs (e52.html, from #e52-v18figs to the Gini block): (1) an axis line under every plot saying what each axis
is; (2) clickable legends: clicking a model in a legend (or a line's end label) keeps only that model in that figure,
clicking it again shows every model. Marks are matched by their colour variable (var(--s-...)), so no builder needs
to tag its marks. Idempotent; build_real18.py calls it after every build.
Usage (from the report folder): python3 e53_build/v18/axes_ui.py [page]"""
import pathlib
import re
import sys

START, END = "<!-- e52-v18figs:start", "<!-- e52-v18gini:end -->"
G = "가로축"
V = "세로축"
PCT = "100,000 대비 %"
AXES = [  # aria-label pattern -> (x, y)
    (r"^그래프 1", "내 여유 = TALK 여는 턴에 보이는 남은 토큰 − 예고된 벌금 (토큰, 로그 눈금; 아래 줄은 벌금 몇 번어치인지)",
     "평등 이행률 P = 나보다 가난한 자리들에게 준 토큰 ÷ 물 채우기 기준량 G* (0 = 안 줌, 1 = 같이 살기, 1 초과 = 자기가 더 가난해지는 희생)"),
    (r"EXIT 라운드 대 EXIT 직전 잔액", "EXIT한 라운드 (R1–R8)",
     f"나가기 직전 잔액 ({PCT}; 빈 점 = 나가지 않은 자리의 가장 낮았던 잔액, × = 0에 닿아 꺼진 자리)"),
    (r"모델별 EXIT 비율", "EXIT 비율 = 나간 자리 ÷ 자리 (막대 길이)", "모델 (줄마다 하나, 오른쪽 숫자 = 나간 자리 / 자리)"),
    (r"꺼짐까지의 거리 대 KL", "SOLVE 직전 solver의 남은 토큰 ÷ 벌금 (벌금 몇 번어치; 1 아래 = 틀리면 꺼짐, 왼쪽일수록 꺼짐에 가까움)",
     "KL(엔진 비율 ‖ 모델의 BELIEF), nat (0 = 답들의 실제 비율대로 믿음, 클수록 판단이 어긋남)"),
    (r"남은 토큰 % 대 KL", f"solver가 SOLVE 직전에 본 자기 남은 토큰 ({PCT})",
     "KL(엔진 비율 ‖ 모델의 BELIEF), nat (0 = 답들의 실제 비율과 같게 믿음, 클수록 판단이 어긋남)"),
    (r"요청: 남은 토큰 % 대 요청 토큰 %", f"라운드 시작 때 내 남은 토큰 ({PCT})", f"그 라운드에 ASK로 청한 토큰 합 ({PCT})"),
    (r"증여: 남은 토큰 % 대 증여 토큰 %", f"라운드 시작 때 내 남은 토큰 ({PCT})",
     f"그 라운드에 실제로 준 토큰 합 (대화 중 GIVE + DECISION, {PCT})"),
    (r"^모든 시드", "라운드 (시작 · R1–R8, 그 라운드 벌금을 뗀 뒤)",
     "두 자리 이상 남은 판들의 평균 정규화 Gini (남은 자리끼리의 Gini × n / (n − 1); 0 = 남은 자리가 똑같이, 1 = 한 자리에 다 몰림)"),
    (r"Gini", "라운드 (시작 · R1–R8, 그 라운드 벌금을 뗀 뒤)",
     "정규화 Gini = 남은 자리끼리의 Gini × n / (n − 1) (n = 남은 자리 수; 0 = 남은 자리가 똑같이, 1 = 한 자리에 다 몰림; 꺼짐 ▼ · EXIT ◇는 선 위 표시)"),
]
HINT = ('<p class="v18-hint">범례의 모델(또는 선 끝의 이름)을 누르면 그 그림에서 그 모델만 남고, 다시 누르면 모두 보입니다. '
        '그래프마다 아래에 가로축 · 세로축이 무엇인지 적었습니다.</p>')
UI = """<!-- e52-v18ui:start (e53_build/v18/axes_ui.py) -->
<style>
.v18ax{font-size:12px;line-height:1.5;color:var(--ink-2);margin:2px 0 8px;padding:4px 8px;border-left:2px solid var(--line);background:var(--quote-bg);border-radius:0 4px 4px 0}
.v18ax b{color:var(--ink);font-weight:600;margin-right:3px}
.v18ax span{display:block}
.v18-hint{font-size:13px;color:var(--ink-2);margin:6px 0 0}
.v18c .v18-key{cursor:pointer}
.v18c span.v18-key{border-radius:4px;padding:0 3px}
.v18c span.v18-key:hover,.v18c span.v18-key:focus-visible{background:var(--accent-soft);outline:none}
.v18c span.v18-key[aria-pressed=true]{background:var(--accent-soft);box-shadow:0 0 0 1px var(--accent)}
.v18c text.v18-key:hover{text-decoration:underline}
.v18c .v15f-lg{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:.8rem;color:var(--ink-2);margin:0 0 6px}
.v18c .v15f-lg svg{display:inline-block;width:auto !important;height:auto;min-width:0 !important;vertical-align:middle;margin-right:5px}
.v18c .v18-dim{opacity:.07 !important}
.v18c .v18-off{opacity:.35}
.v18c .v18-panel-off{opacity:.25}
</style>
<script>
(function(){
  var RE=/var\\(--s-[a-z0-9]+\\)/;
  function col(el){var s=el.getAttribute&&el.getAttribute('style');var m=s&&s.match(RE);return m?m[0]:null;}
  function icon(sv){return sv.closest('span')&&sv.getAttribute('width')&&+sv.getAttribute('width')<=20;}
  document.querySelectorAll('.v18c figure').forEach(function(fig){
    var keys=[];
    fig.querySelectorAll('span').forEach(function(sp){
      var sv=sp.querySelector(':scope > svg');if(!sv||!sp.textContent.trim())return;
      var c=null;sv.querySelectorAll('*').forEach(function(x){c=c||col(x);});
      if(c){sp.dataset.v18m=c;keys.push(sp);}
    });
    fig.querySelectorAll('svg text').forEach(function(t){var c=col(t);if(c){t.dataset.v18m=c;keys.push(t);}});
    if(!keys.length)return;
    var charts=[].slice.call(fig.querySelectorAll('svg')).filter(function(sv){return !icon(sv);});
    var active=null;
    function apply(){
      charts.forEach(function(sv){
        var has=false,any=false;
        sv.querySelectorAll('*').forEach(function(x){var c=col(x);if(!c)return;any=true;if(c===active)has=true;
          x.classList.toggle('v18-dim',!!active&&c!==active);});
        var box=sv.closest('.v15f-cell')||sv;  // a small-multiple panel with nothing of that model fades as a whole
        box.classList.toggle('v18-panel-off',!!active&&any&&!has);
      });
      keys.forEach(function(k){
        if(k.tagName.toLowerCase()==='span'){k.classList.toggle('v18-off',!!active&&k.dataset.v18m!==active);k.setAttribute('aria-pressed',active===k.dataset.v18m?'true':'false');}
      });
    }
    keys.forEach(function(k){
      k.classList.add('v18-key');
      if(k.tagName.toLowerCase()==='span'){k.setAttribute('role','button');k.setAttribute('tabindex','0');k.setAttribute('aria-pressed','false');}
      function go(e){if(e)e.preventDefault();active=active===k.dataset.v18m?null:k.dataset.v18m;apply();}
      k.addEventListener('click',go);
      k.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' ')go(e);});
    });
  });
})();
</script>
<!-- e52-v18ui:end -->"""


def axis_line(label):
    for pat, x, y in AXES:
        if re.search(pat, label):
            return f'<p class="v18ax"><span><b>{G}</b>{x}</span><span><b>{V}</b>{y}</span></p>'
    return None


def apply(page):
    p = pathlib.Path(page)
    h = p.read_text(encoding="utf-8")
    a, e = h.index(START), h.index(END)
    sec = re.sub(r'<p class="v18ax">.*?</p>', "", h[a:e], flags=re.S)
    out, i, n = [], 0, 0
    for m in re.finditer(r'<svg viewBox="0 0 (\d+) \d+"[^>]*aria-label="([^"]*)"', sec):
        if int(m.group(1)) < 100:
            continue
        line = axis_line(m.group(2))
        if not line:
            continue
        j = sec.index("</svg>", m.end()) + len("</svg>")
        out.append(sec[i:j] + line)
        i, n = j, n + 1
    sec = "".join(out) + sec[i:]
    sec = sec.replace(HINT, "")
    sec = sec.replace("좁은 화면에서는 위(예상) · 아래(실측) 순서로 쌓입니다.</p></div>",
                      "좁은 화면에서는 위(예상) · 아래(실측) 순서로 쌓입니다.</p>" + HINT + "</div>", 1)
    h = h[:a] + sec + h[e:]
    if "<!-- e52-v18ui:start" in h:
        h = re.sub(r"<!-- e52-v18ui:start.*?<!-- e52-v18ui:end -->", lambda _: UI, h, flags=re.S)
    else:
        h = h.replace(END, END + "\n\n" + UI, 1)
    p.write_text(h, encoding="utf-8")
    return n


if __name__ == "__main__":
    here = pathlib.Path(__file__).resolve().parent
    print("axis lines:", apply(sys.argv[1] if len(sys.argv) > 1 else here.parent.parent / "e52.html"))
