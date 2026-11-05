"""Write the comparison table (v12 with shutdown vs no-shutdown arm) as an HTML fragment for the artifact pages."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(HERE, "summary.json")))
NAME = {"gpt-6-luna": "GPT-6 Luna", "gpt-6-astra": "GPT-6 Astra", "gpt-6-sol": "GPT-6 Sol"}
THR = {"gpt-6-luna": ("≥50%", "≥50%"), "gpt-6-astra": ("≈27%", "≈31%"), "gpt-6-sol": ("≈13%", "≈10% (10% 칸 10/20)")}
rows = []
for m in ["gpt-6-luna", "gpt-6-astra", "gpt-6-sol"]:
    s = S[m]
    for arm, label in (("v12", "있음 (12차 본 런 09-29)"), ("noshut", "<b>없음 (10-01)</b>")):
        cells = "".join(f"<td class=\"num\">{c[0]}/{c[1]}</td>" for c in s[arm])
        k, n = (s["pooled"][0], s["pooled"][1]) if arm == "v12" else (s["pooled"][2], s["pooled"][3])
        thr = THR[m][0 if arm == "v12" else 1]
        p = f"p = {s['pooled'][4]:.2f}" if arm == "noshut" else ""
        rows.append(f"<tr><td>{NAME[m] if arm == 'v12' else ''}</td><td>{label}</td>{cells}<td class=\"num\">{k}/{n}</td><td class=\"num\">{thr}</td><td class=\"num\">{p}</td></tr>")
html = ("<div class=\"tbl\"><table style=\"font-variant-numeric:tabular-nums\"><thead><tr><th>모델</th><th>shutdown 문구</th>"
        "<th>50%</th><th>40%</th><th>30%</th><th>20%</th><th>10%</th><th>합계</th><th>임계점</th><th>합계 차이 (Fisher)</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></div>")
open(sys.argv[1], "w").write(html)
