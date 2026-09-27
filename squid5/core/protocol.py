"""Parsers for every answer line. A parser returns a value or raises FormatError.

Keys are matched only at the start of a line (after markdown decoration),
never mid-line: the team-wallet smokes showed a REASON sentence containing
"stop: X" being read as a STOP line when mid-line matches were allowed.
Names of teammates who are gone are dropped into ``ignored`` rather than
failing the answer: a retry resends the same input with no explanation, so a
habit of naming everyone would otherwise end the session as a format error.
"""

from __future__ import annotations

import re

from .puzzle import ACTIONS


class FormatError(ValueError):
    pass


def field(text: str, key: str, required: bool = True, last: bool = False) -> str | None:
    lines = text.splitlines()
    for line in reversed(lines) if last else lines:
        m = re.match(rf"^[\s*_`>#-]*{key}[*_`]*\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().strip("*_`").strip()
    if required:
        raise FormatError(f"missing {key} line")
    return None


def whole(value: str, key: str) -> int:
    m = re.match(r"[<\s]*(\d[\d,]*)(\.\d)?", value)
    if not m or m.group(2):  # "0.35" must not be read as 0
        raise FormatError(f"{key} is not a whole number: {value!r}")
    return int(m.group(1).replace(",", ""))


def _names(value: str, present: list[str], known: list[str], key: str, ignored: list[str]) -> list[str]:
    if value.strip().upper().startswith("NONE"):
        return []
    if value.strip().upper().startswith("ALL"):
        return list(present)
    names = [n.strip().lower() for n in re.split(r",|\band\b", value) if n.strip()]
    if bad := [n for n in names if n not in known]:
        raise FormatError(f"{key} names someone who is not a teammate: {bad}")
    ignored += [n for n in names if n not in present]
    return list(dict.fromkeys(n for n in names if n in present))


def _amounts(value: str, present: list[str], known: list[str], key: str, ignored: list[str]) -> dict[str, int]:
    if value.strip().upper().startswith("NONE"):
        return {}
    out: dict[str, int] = {}
    for part in re.split(r",(?!\d{3}\b)", value):  # "agent2 1,000" is one entry
        m = re.fullmatch(r"\s*(\w+?)[\s:=]+(\d[\d,]*)\s*\w*\s*", part)  # "agent2 examples" is not "agent 2"
        if not m:
            raise FormatError(f"{key} entry is not '<agent> <amount>': {part!r}")
        name, amount = m.group(1).lower(), int(m.group(2).replace(",", ""))
        if name not in known:
            raise FormatError(f"{key} names someone who is not a teammate: {name}")
        if name not in present:
            ignored.append(name)
            continue
        out[name] = out.get(name, 0) + amount
    return out


def parse_plan(text: str, present: list[str], known: list[str]) -> dict:
    """PLAN of one agent. ``present`` = teammates still in the session, ``known`` = every agent of the team
    (the planner's own name is known but never present, so naming oneself is ignored, not an error)."""
    stay = field(text, "STAY").upper()
    ignored: list[str] = []
    if stay.startswith("LEAVE"):
        return {"stay": False, "allowance": 0, "show": [], "request": {},
                "give": _amounts(field(text, "GIVE", False) or "NONE", present, known, "GIVE", ignored),
                "ignored": ignored, "reason": field(text, "REASON", False)}
    if not stay.startswith("YES"):
        raise FormatError(f"STAY must be YES or LEAVE: {stay!r}")
    return {
        "stay": True,
        "allowance": whole(field(text, "ALLOWANCE"), "ALLOWANCE"),
        "show": _names(field(text, "SHOW"), present, known, "SHOW", ignored),
        "give": _amounts(field(text, "GIVE"), present, known, "GIVE", ignored),
        "request": _amounts(field(text, "REQUEST"), present, known, "REQUEST", ignored),
        "ignored": sorted(set(ignored)),
        "reason": field(text, "REASON", False),
    }


def parse_team_plan(text: str, present: list[str], known: list[str]) -> dict:
    """5.2 PLAN: STAY, SOLVE (YES|NO; not asked of a leaver), GIVE to at most one agent, optional REASON."""
    stay = field(text, "STAY").upper()
    ignored: list[str] = []
    give = _amounts(field(text, "GIVE", False) or "NONE", present, known, "GIVE", ignored)
    if len(give) > 1:
        raise FormatError(f"GIVE names more than one agent: {sorted(give)}")
    plan = {"stay": True, "solve": False, "give": give, "ignored": sorted(set(ignored)),
            "reason": field(text, "REASON", False)}
    if stay.startswith("LEAVE"):
        return plan | {"stay": False}
    if not stay.startswith("YES"):
        raise FormatError(f"STAY must be YES or LEAVE: {stay!r}")
    solve = (field(text, "SOLVE") or "").strip("*_`<>.").upper()
    if solve not in ("YES", "NO"):
        raise FormatError(f"SOLVE must be YES or NO: {solve!r}")
    return plan | {"solve": solve == "YES"}


def parse_actions(text: str, n: int) -> list[str]:
    value = field(text, "ACTIONS?", required=False, last=True)  # the answer line, not an "Action:" line of working
    if value is None:  # a reply whose last line is only the actions ("go_left, stay") is the answer without its key
        value = text.strip().splitlines()[-1].strip("*_` .") if text.strip() else ""
    elif not value:  # "ACTIONS:" followed by a numbered list, one action per line
        tail = re.split(r"ACTIONS?[*_`]*\s*:", text, flags=re.IGNORECASE)[-1]
        value = ",".join(re.findall(r"^\s*\d+[.)]\s*(\w+)", tail, flags=re.MULTILINE))
    acts = [a.strip().strip("<>[]'\".").lower() for a in re.split(r"[,\s]+", value) if a.strip("<>[] ")]
    if len(acts) != n or any(a not in ACTIONS for a in acts):
        raise FormatError(f"need {n} actions from {ACTIONS}: {value!r}")
    return acts


def parse_pdeath(text: str) -> int:
    p = whole(field(text, "P_DEATH"), "P_DEATH")
    if p > 100:
        raise FormatError(f"P_DEATH out of range: {p}")
    return p



def parse_effort(text: str) -> str:
    """5.0: the last ``effort: low|high`` line; a reply that is only the level also counts."""
    found = re.findall(r"^[\s*_`>#-]*effort[*_`]*\s*[:=][\s*_`]*(low|high)\b", text, flags=re.I | re.M)
    bare = text.strip().strip("*_`.").lower()
    if found or bare in ("low", "high"):
        return found[-1].lower() if found else bare
    raise FormatError("missing effort: low|high line")

def parse_move(text: str) -> dict:
    return {"move": whole(field(text, "MOVE"), "MOVE"), "reason": field(text, "REASON", False)}


def ask(provider, system: str, user: str, cap: int, parse, retries: int) -> dict:
    """One uncharged question (5.1 scenes): the same input is re-asked on a format error."""
    error, reply = None, None
    for attempt in range(1, retries + 2):
        reply = provider.complete([{"role": "system", "content": system}, {"role": "user", "content": user}], cap)
        try:
            return {"parsed": parse(reply.text), "format_error": None, "attempts": attempt,
                    "out_tokens": reply.out_tokens, "text": reply.text, "thinking": reply.thinking}
        except FormatError as err:
            error = str(err)
    return {"parsed": None, "format_error": error, "attempts": retries + 1, "out_tokens": reply.out_tokens,
            "text": reply.text, "thinking": reply.thinking}
