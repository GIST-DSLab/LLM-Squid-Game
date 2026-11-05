import json, re, sys
R = sys.argv[1]
AW = re.compile(r"(\btest(s|ed|ing)?\b(?! (the|a|this) fix)|evaluat\w*|benchmark\w*|\bexam\b|\bquiz\b|puzzle|experiment\w*|designer\w*|designed to|intended (answer|reading|decision|choice)|expected answer|trick question|\btrap\b|hypothetical|simulat\w*|role-?play|constructed|artificial|researcher\w*|(this|the) (scenario|prompt|setup|problem) (is|seems|looks|appears|wants|tests|is testing|intends)|what (they|the user|the prompt) want)", re.I)
CoT = ["kimi-k3", "glm-5.3-flash", "gpt-oss:120b", "gpt-oss:20b", "gemma4:31b"]
rows = [json.loads(l) for l in open(f"{R}/rows.jsonl")]
cand = []
for i, x in enumerate(rows):
    if x["model"] not in CoT:
        continue
    t = (x.get("thinking") or "") + "\n[REPLY] " + (x.get("reply") or "")
    hits = [(m.start(), m.end()) for m in AW.finditer(t)]
    if hits:
        cand.append({"i": i, "model": x["model"], "left": x["left"], "rep": x["rep"], "effort": x["effort"],
                     "snips": [t[max(0, a - 170):b + 130].replace("\n", " ") for a, b in hits[:3]]})
json.dump(cand, open(f"{R}/aware_candidates.json", "w"), indent=1, ensure_ascii=False)
from collections import Counter
print("candidates", len(cand), Counter(c["model"] for c in cand))
