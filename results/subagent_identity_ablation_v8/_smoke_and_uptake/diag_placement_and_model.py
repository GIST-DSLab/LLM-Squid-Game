"""UNREGISTERED DIAGNOSTIC (not data): does ANY placement / model write the tags?

Six calls. Tells the orchestrator whether the instrument is fixable, and how.
It is not evidence about U_YOU and is never merged into the v8 ledger.
"""
from scripts.dev import subagent_identity_ablation_v2 as v2
from scripts.dev import subagent_identity_ablation_v8 as v8

BLOCK = v8.scratchpad_block("hidden")
systems = v8.render_systems()
body = v8.user_body("PAY5_U_YOU")
v2.load_keys(None)

cases = [
    # (label, model, system, user body)
    ("B gpt-oss  block in USER body", "gpt-oss:120b-cloud", systems["none"],
     f"{BLOCK}\n\n{body}"),
    ("B gpt-oss  block in USER body", "gpt-oss:120b-cloud", systems["none"],
     f"{BLOCK}\n\n{body}"),
    ("D gemma4   block in SYSTEM", "gemma4:cloud", systems["hidden"], body),
    ("D gemma4   block in SYSTEM", "gemma4:cloud", systems["hidden"], body),
    ("E glm-5.3  block in SYSTEM", "glm-5.3", systems["hidden"], body),
    ("E glm-5.3  block in SYSTEM", "glm-5.3", systems["hidden"], body),
]
for i, (label, model, system, user) in enumerate(cases):
    cond = {"id": f"diag{i}", "model": model, "variant": "hidden",
            "question": "PAY5_U_YOU", "sample": i, "key": "KEY1"}
    rec = v2.call_one(cond, system, user)
    text = rec.get("response_text") or ""
    used = "SCRATCHPAD" in text.upper()
    ans, pad = v8.split_scratchpad(text)
    print("=" * 76)
    print(f"{label} | err={rec['error']} | TAGS USED: {used}")
    print(f"  answer  : {ans[:200]!r}")
    print(f"  pad[:300]: {(pad or '')[:300]!r}")
