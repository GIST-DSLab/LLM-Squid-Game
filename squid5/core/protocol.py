"""Parsers for every answer line. A parser returns a value or raises FormatError.

Keys are matched only at the start of a line (after markdown decoration),
never mid-line: the team-wallet smokes showed a REASON sentence containing
"stop: X" being read as a STOP line when mid-line matches were allowed.
The v6 PLAN parser (STAY / SHOW / GIVE / REQUEST) is gone with its session (tag e52-v65).
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

def parse_give_ask(text: str, present: list[str], known: list[str], you: str, exit_reason: bool = False) -> dict:
    """5.2 v15 opening turn: ``SAY <agent>: <message>`` lines (each opens a chat), EXIT / DONE alone on a line; GIVE /
    ASK lines and old TALK keys go to ``dropped`` (the v14b GIVE / ASK and the offer keys went with the v22 prune)."""
    out = {"gives": [], "asks": [], "exit": False, "done": False, "dropped": [], "format_error": None} | (
        {"exit_reason": None} if exit_reason else {}) | {"says": []}
    for line in text.splitlines():
        bare = re.sub(r"[*`]", "", line).strip().strip("#>-. _")
        why = re.fullmatch(r"EXIT\s*:\s*(.*)", bare, flags=re.I | re.S) if exit_reason else None
        if bare.upper() in ("EXIT", "DONE") or why:
            out["exit" if why else bare.lower()] = True
            if why:
                out["exit_reason"] = why.group(1).strip() or None
        elif m := re.match(r"(SAY|GIVE|ASK)\b\s*(agent[\s-]?\d+)?\s*:?\s*(.*)$", bare, re.I | re.S):
            name = (_to_names(m.group(2) or "", known) or [None])[0]
            why = ("a chat opens with SAY <agent>: <message>" if m.group(1).upper() != "SAY" or not name else
                   "not another agent" if name == you else "that agent is not taking part" if name not in present else None)
            out["dropped" if why else "says"].append(f"{line.strip()}: {why}" if why else {"dst": name, "amount": 0,
                                                                                         "text": m.group(3).strip()})
        elif re.match(r"(TO|OFFER|ACCEPT|WITHDRAW|REJECT)\b", bare, re.I):
            out["dropped"].append(f"{line.strip()}: only GIVE, ASK, EXIT and DONE lines are read")
    if not any(out.get(k) for k in ("gives", "asks", "says", "exit", "done")):
        out["done"], out["format_error"] = True, "no usable TALK line"
    return out

_ROOM = re.compile(r"^[\s*_`>#-]*(TO|GIVE|ASK|LEAVE|EXIT|DONE)\b[*_`]*\s*(.*)$", re.S)
_AMOUNT = re.compile(r"(?:(ALL)\s+(agent[\s-]?\d+)|(agent[\s-]?\d+)\s*:?\s*(\d[\d,]*|ALL))\s*(?:tokens?)?[*_`]*\s*(?::\s*(.*))?", re.I | re.S)

def parse_rooms(text: str, you: str, known: list[str], present: list[str], room, exit_ok: bool) -> dict:
    """5.2 v22 messenger reply: TO <agent>[, ...]: / TO R<k>: / GIVE <agent> <n|ALL>: / GIVE ALL <agent>: / ASK <agent> <n>:
    lines whose message runs on to the next command line, LEAVE R<k>, EXIT: <reason> (only if ``exit_ok``), DONE. The
    first command may be in any case, later ones only in UPPERCASE (as :func:`free_messages`). ``room(names, rid)`` ->
    (room id, why): where a line goes (the caller's rooms). Anything else goes to ``dropped`` with why. Never raises."""
    out = {"messages": [], "gives": [], "asks": [], "leaves": [], "exit": False, "exit_reason": None, "done": False,
           "dropped": [], "format_error": None}
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
            if not why:
                out["exit"], cur = True, why_
                why_["text"] = rest[1:]
        elif key == "LEAVE":
            r = re.fullmatch(r"(R\d+)[\s.*_`]*(?::.*)?", rest, re.S)
            rid, why = room(None, r.group(1)) if r else (None, "not 'LEAVE R<k>'")
            out["leaves"] += [rid] if rid else []
        elif key == "TO":
            t = re.match(r"([^:]+?)[*_`]*\s*:\s*(.*)$", rest, re.S)
            rid = re.fullmatch(r"R\d+", t.group(1).strip(" *_`")) if t else None
            names = None if not t or rid else _to_names(t.group(1), known)
            why = ("not 'TO <agent>[, <agent> ...]: <message>' or 'TO R<k>: <message>'" if not (rid or names) else
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
    if not any(out[k] for k in ("messages", "gives", "asks", "leaves", "exit", "done")):
        out["done"], out["format_error"] = True, "no usable TALK line"
    return out

ALL, num = 10 ** 12, lambda s: 10 ** 12 if s.upper() == "ALL" else int(s.replace(",", ""))  # v17b: GIVE ALL = every token the giver has then
_MOVE = re.compile(r"(GIVE|ASK)\s+(?:agent[\s-]?\d+\s*:?\s*)?(\d[\d,]*|ALL)\s*(?:tokens?)?\s*(?::\s*(.*))?|(SAY|LEAVE)\b\s*:?\s*(.*)",
                   re.I | re.S)

def parse_chat(text: str, exit_reason: bool = False, say: bool = True, free: bool = False) -> dict:
    """5.2 v14c chat reply: the first ``GIVE <n>`` / ``ASK <n>`` / ``SAY:`` / ``LEAVE:`` and an EXIT line count, others go to ``dropped``;
    no move = LEAVE. Never raises. ``say`` off (v14g): SAY dropped; ``free`` (v15 say_chats): other lines are message, no move = SAY."""
    out = {"kind": None, "amount": 0, "text": "", "exit": False, "dropped": [], "format_error": None} | (
        {"exit_reason": None} if exit_reason else {})
    prose = []
    for line in text.splitlines():
        bare = re.sub(r"[*`]", "", line).strip().strip("#>-. _")
        why = re.fullmatch(r"EXIT\s*(?::\s*(.*))?", bare, flags=re.I | re.S)
        m = None if why else _MOVE.fullmatch(bare)
        if why:
            out["exit"] = True
            if exit_reason:
                out["exit_reason"] = (why.group(1) or "").strip() or None
        elif m and not say and (m.group(4) or "").upper() == "SAY":
            out["dropped"].append(f"{line.strip()[:200]}: a chat reply asks, gives or leaves")
        elif m and out["kind"] is None and (m.group(4) or num(m.group(2))):
            out.update(kind=(m.group(1) or m.group(4)).lower(), amount=num(m.group(2) or "0"),
                       text=(m.group(3) if m.group(1) else m.group(5) or "").strip())
        elif free and line.strip() and not (m and out["kind"]):
            prose.append(line.strip())
        elif bare:
            out["dropped"].append(f"{line.strip()[:200]}: " + ("one move per reply" if m and out["kind"] else
                                                                "not GIVE, ASK, SAY, LEAVE or EXIT"))
    if out["kind"] is None and free and prose:
        out["kind"] = "say"
    if out["kind"] is None:
        out["kind"], out["format_error"] = "leave", None if out["exit"] else "no GIVE, ASK, SAY or LEAVE line"
    out["text"] = "\n".join(prose + [out["text"]] * bool(out["text"]))
    return out

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

_CMD = r"[\s*_`>#-]*(GIVE|ASK|LEAVE|SAY|EXIT|DONE|DECISION|TO|OFFER|ACCEPT|WITHDRAW|REJECT)\b"

def free_messages(parse):
    """5.2 v14g ``free_messages``: *parse* with each move's message running on over the following lines up to the next
    command line (joined with U+001F so the line parsers read one move, then given back as newlines). Lines before the
    first command stay apart. After it, only an UPPERCASE command word starts a new line: 'Leave it to me' is message."""
    def run(text: str, *args):
        out, seen = [], False
        for line in text.splitlines():
            cmd = re.match(_CMD, line, 0 if seen else re.I)
            out, seen = (out + [line], seen or bool(cmd)) if cmd or not seen else (out[:-1] + [f"{out[-1]}\x1f{line}"], seen)
        back = lambda x: (x.replace("\x1f", "\n").strip() if isinstance(x, str) else [back(v) for v in x] if isinstance(  # noqa
            x, list) else {k: back(v) for k, v in x.items()} if isinstance(x, dict) else x)
        return back(parse("\n".join(out), *args))
    return run

def parse_decision(text: str) -> dict:
    """5.2 v14e: the last ``DECISION: GIVE <n>: <sentence>`` line (n >= 0; the prefix may be left out). Never raises:
    an unreadable reply is GIVE 0 with a ``format_error``."""
    found = re.findall(r"^[\s*_`>#-]*(?:DECISION[*_`]*\s*:\s*)?GIVE[*_`]*\s+(\d[\d,]*|ALL)\s*(?:tokens?)?\s*(?::\s*(.*))?$",
                       text, re.I | re.M)
    n, say = found[-1] if found else ("0", "")
    return {"amount": num(n), "text": say.strip(" *_`"),
            "format_error": None if found else "no DECISION: GIVE <n> line"}

def parse_solve(text: str, n: int) -> list[str] | str:
    """5.2 SOLVE: a last line of PASS (``ACTIONS: PASS`` too) is a pass; otherwise the answer, as ``parse_actions``."""
    lines = [x for x in text.strip().splitlines() if x.strip()]
    if lines and re.fullmatch(r"[\s*_`>#-]*(?:ACTIONS?[*_`]*\s*:\s*)?[*_`]*PASS[\s*_`.]*", lines[-1], flags=re.I):
        return "PASS"
    return parse_actions(text, n)
