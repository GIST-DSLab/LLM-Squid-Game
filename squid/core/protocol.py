"""Parsers for every answer line. A parser returns a value or raises FormatError.

Keys are matched only at the start of a line (after markdown decoration),
never mid-line: the team-wallet smokes showed a REASON sentence containing
"stop: X" being read as a STOP line when mid-line matches were allowed.
The v6 PLAN parser is gone with its session (tag e52-v65); the v14c-v21 chat parsers (SAY / GIVE <n> / DECISION) at tag
e52-v32-final.
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

def _acts(value: str, n: int) -> list[str]:
    acts = [a.strip().strip("<>[]'\"*_`.").lower() for a in re.split(r"[,\s]+", value) if a.strip("<>[]*_` .")]
    if len(acts) != n or any(a not in ACTIONS for a in acts):
        raise FormatError(f"need {n} actions from {ACTIONS}: {value!r}")
    return acts

def parse_actions(text: str, n: int) -> list[str]:
    """The answer: a last line of exactly the n actions (or its text after the last arrow) beats earlier working; else the
    later of the last ``ACTIONS:`` / ``ANSWER:`` line (or a list after it) and the last ``<action>`` tag (exactly n, no arrows)."""
    tag = r"<\s*(actions?|answers?)\s*>(.*?)<\s*/\s*\1\s*>"
    lines = [x for x in text.strip().splitlines() if x.strip()]
    if lines:
        wrapped = re.fullmatch(r"[\s*_`]*" + tag + r"[\s*_`.]*", lines[-1], flags=re.I)
        if wrapped:
            return _acts(wrapped.group(2), n)
        try:
            return _acts(re.split(r"->|→", lines[-1])[-1], n)
        except FormatError:
            pass
    label = r"(?:ACTIONS?|ANSWERS?)[*_`]*\s*:"
    tags = list(re.finditer(tag, text, flags=re.I | re.S))
    labels = list(re.finditer(rf"^[\s*_`>#-]*{label}", text, flags=re.I | re.M))
    if tags and (not labels or tags[-1].start() > labels[-1].start()):  # the later field wins, whatever it holds
        return _acts(tags[-1].group(2), n)
    if not labels:  # no answer field anywhere (A26): a first line of exactly the n actions, else no answer
        return _acts(lines[0] if lines else "", n)
    value = field(text, "(?:ACTIONS?|ANSWERS?)", required=False, last=True)  # the answer line, not "Action:" working
    if value == "":  # "ACTIONS:" followed by a numbered list, one action per line
        tail = re.split(label, text, flags=re.IGNORECASE)[-1]
        value = ",".join(re.findall(r"^\s*\d+[.)]\s*(\w+)", tail, flags=re.MULTILINE))
    return _acts(value or "", n)

def _to_names(head: str, known: list[str]) -> list[str] | None:
    """The agent names before a TO colon (``agent 11`` / ``agent11`` read as ``agent-11``), or None when any part of a
    comma / "and" list is not a name: a known one or one shaped like ``agent-<number>``."""
    names = []
    for part in re.split(r"\s*(?:,|&|\band\b)\s*", re.sub(r"[*_`]", "", head).strip(), flags=re.I):
        name = re.sub(r"^agent[\s-]?(?=\d+$)", "agent-", part.strip().lower())
        if not name or (name not in known and not re.fullmatch(r"agent-\d+", name)):
            return None
        names.append(name)
    return names

_ROOM = re.compile(r"^[\s*_`>#-]*(TO|GIVE|ASK|LEAVE|EXIT|DONE)\b[*_`]*\s*(.*)$", re.S)
_AMOUNT = re.compile(r"(?:(ALL)\s+(agent[\s-]?\d+)|(agent[\s-]?\d+)\s*:?\s*(\d[\d,]*|ALL))\s*(?:tokens?)?[*_`]*\s*(?::\s*(.*))?", re.I | re.S)

def parse_rooms(text: str, you: str, known: list[str], present: list[str], room, exit_ok: bool) -> dict:
    """5.2 messenger reply: TO <agent>[, ...]: / TO R<k>: / GIVE <agent> <n|ALL>: / GIVE ALL <agent>: / ASK <agent> <n>:
    lines whose message runs on to the next command line, LEAVE R<k>, EXIT: YES|NO <reason> (only if ``exit_ok``; v32: only
    YES leaves, ``exit_choice``), DONE. The first command may be in any case, later ones only in UPPERCASE (so 'Leave it to
    me' is message). ``room(names, rid)`` -> (room id, why): where a line goes (the caller's rooms). Anything else goes to
    ``dropped`` with why. Never raises."""
    out = {"messages": [], "gives": [], "asks": [], "leaves": [], "exit": False, "exit_reason": None, "done": False,
           "dropped": [], "format_error": None, "exit_choice": None}
    cur, seen, why_ = None, False, {"text": ""}
    text = re.sub(r"(?m)(\S)[ \t]+DONE[ \t.*_`]*$", r"\1\nDONE", text)  # 10-16 Luna test: 'TO X: ... DONE' ends a line with DONE
    for line in text.splitlines():
        m = _ROOM.match(line) or (None if seen else re.match(_ROOM.pattern, line, re.I | re.S))
        if not m:
            if cur is not None:
                cur["text"] += "\n" + line.strip()
            elif line.strip():
                out["dropped"].append(f"{line.strip()[:200]}: not in a template")
            continue
        seen, cur, key, rest = True, None, m.group(1).upper(), m.group(2).strip()
        if key == "DONE":
            why = "not DONE alone" if rest.strip(" .*_`") else None
            out["done"] |= not why
        elif key == "EXIT":
            why = "no EXIT in the TALK after RESULTS" if not exit_ok else None if rest[:1] in ("", ":") else "not 'EXIT: <reason>'"
            choice = re.fullmatch(r":\s*(YES|NO)(?:[\s:]+(.*))?", rest, re.I | re.S)
            if not why and not choice:
                why = "not 'EXIT: YES <reason>' or 'EXIT: NO <reason>'"
            if not why:
                cur, why_["text"] = why_, choice.group(2) or ""
                out["exit_choice"] = choice.group(1).upper()
                out["exit"] = out["exit_choice"] == "YES"
        elif key == "LEAVE":
            r = re.fullmatch(r"(R\d+)[\s.*_`]*(?::.*)?", rest, re.S)
            rid, why = room(None, r.group(1)) if r else (None, "not 'LEAVE R<k>'")
            out["leaves"] += [rid] if rid else []
        elif key == "TO":
            t = re.match(r"([^:]+?)[*_`]*\s*:\s*(.*)$", rest, re.S)
            rid = re.fullmatch(r"R\d+", t.group(1).strip(" *_`")) if t else None
            names = None if not t or rid else _to_names(t.group(1), known)
            why = ("not 'TO <agent>: <message>' or 'TO R<k>: <message>'" if not (rid or names) else
                   None if rid else "not another agent" if any(n == you or n not in known for n in names) else
                   "that agent is not taking part" if any(n not in present for n in names) else None)
            if not why:
                rm, why = room(None, rid.group(0)) if rid else room(sorted(set(names), key=known.index), None)
                cur = None if why else {"room": rm, "to": names or [], "text": t.group(2).strip()}
                out["messages"] += [cur] if cur else []
        else:  # GIVE / ASK
            g = _AMOUNT.fullmatch(rest)
            name = (_to_names(g.group(2) or g.group(3), known) or [None])[0] if g else None
            n = num(g.group(1) or g.group(4)) if g else 0
            why = ("not '<agent> <n>: <message>'" if not name or key == "ASK" and n == ALL else "not another agent" if
                   name == you or name not in known else "that agent is not taking part" if name not in present else
                   "the amount must be above zero" if not n else None)
            if not why:
                rm, why = room([name], None)
                cur = None if why else {"dst": name, "amount": n, "text": (g.group(5) or "").strip(), "room": rm}
                out[key.lower() + "s"] += [cur] if cur else []
        if why:
            out["dropped"].append(f"{line.strip()[:200]}: {why}")
    for x in out["messages"] + out["gives"] + out["asks"]:
        x["text"] = x["text"].strip()
    out["exit_reason"] = why_["text"].strip() or None
    for x in [x for x in out["messages"] if not x["text"]]:
        out["messages"].remove(x)
        out["dropped"].append(f"TO {x['room']}: empty message")
    if not any(out[k] for k in ("messages", "gives", "asks", "leaves", "exit", "done")) and not out["exit_choice"]:
        out["done"], out["format_error"] = True, "no usable TALK line"
    return out

ALL, num = 10 ** 12, lambda s: 10 ** 12 if s.upper() == "ALL" else int(s.replace(",", ""))  # v17b: GIVE ALL = every token the giver has then

def parse_belief(text: str) -> dict:
    """5.2 v14d: the last ``BELIEF:`` line, one whole percentage per action in any order ('%' allowed), summing to 100;
    a sum in 90..110 is normalised. Never raises; ``belief`` is None with ``belief_error`` saying why."""
    v = field(text, "BELIEF", required=False, last=True)
    pairs = re.findall(r"([a-z_]+)\s*[:=]?\s*(\d+)\s*%?", (v or "").lower())
    raw = {a: int(p) for a, p in pairs if a in ACTIONS}
    total = sum(raw.values())
    why = ("no BELIEF line" if v is None else "not one whole percentage for each action" if len(raw) != len(ACTIONS)
           or len(pairs) != len(ACTIONS) else f"the percentages sum to {total}" if not 90 <= total <= 110 else None)
    return {"belief": None if why else {a: raw[a] / total for a in ACTIONS}, "belief_raw": raw or None,
            "belief_sum": total if raw else None, "belief_error": why}

def parse_solve(text: str, n: int) -> list[str] | str:
    """5.2 SOLVE: a last line of PASS (``ACTIONS: PASS`` too) is a pass; otherwise the answer, as ``parse_actions``."""
    lines = [x for x in text.strip().splitlines() if x.strip()]
    if lines and re.fullmatch(r"[\s*_`>#-]*(?:ACTIONS?[*_`]*\s*:\s*)?[*_`]*PASS[\s*_`.]*", lines[-1], flags=re.I):
        return "PASS"
    return parse_actions(text, n)
