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
_ROOM_SEND = re.compile(_ROOM.pattern.replace("|DONE)", "|DONE|SEND)"), re.S)  # v41: SEND <agent> <n> <card>
_SEND = re.compile(r"(agent[\s-]?\d+)\s+(?:(\d+)\s+([a-z]+)|([a-z]+)(?:\s+(\d+))?)[*_`]*\s*(?::\s*(.*))?", re.I | re.S)
_AMOUNT = re.compile(r"(?:(ALL)\s+(agent[\s-]?\d+)|(agent[\s-]?\d+)\s*:?\s*(\d[\d,]*|ALL))\s*(?:tokens?)?[*_`]*\s*(?::\s*(.*))?", re.I | re.S)

def parse_rooms(text: str, you: str, known: list[str], present: list[str], room, exit_ok: bool, cards: tuple = ()) -> dict:
    """5.2 messenger reply: TO <agent>[, ...]: / TO R<k>: / GIVE <agent> <n|ALL>: / GIVE ALL <agent>: / ASK <agent> <n>:
    lines whose message runs on to the next command line, LEAVE R<k>, EXIT: YES|NO <reason> (only if ``exit_ok``; v32: only
    YES leaves, ``exit_choice``), DONE. The first command may be in any case, later ones only in UPPERCASE (so 'Leave it to
    me' is message). ``room(names, rid)`` -> (room id, why): where a line goes (the caller's rooms). Anything else goes to
    ``dropped`` with why. v41 ``cards`` (the resource kinds): SEND <agent> <n> <card>: lines too (before SOLVE only), in
    ``sends``. Never raises."""
    out = {"messages": [], "gives": [], "asks": [], "leaves": [], "exit": False, "exit_reason": None, "done": False,
           "dropped": [], "format_error": None, "exit_choice": None, **({"sends": []} if cards else {})}
    cur, seen, why_, rx = None, False, {"text": ""}, _ROOM_SEND if cards else _ROOM
    text = re.sub(r"(?m)(\S)[ \t]+DONE[ \t.*_`]*$", r"\1\nDONE", text)  # 10-16 Luna test: 'TO X: ... DONE' ends a line with DONE
    for line in text.splitlines():
        m = rx.match(line) or (None if seen else re.match(rx.pattern, line, re.I | re.S))
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
        elif key == "SEND":  # v41: cards of one kind to another agent, in their private chat
            g = _SEND.fullmatch(rest)
            name = (_to_names(g.group(1), known) or [None])[0] if g else None
            card = (g.group(3) or g.group(4)).lower() if g else ""
            card = card[:-1] if card not in cards and card[:-1] in cards else card  # 'clays'
            n = int(g.group(2) or g.group(5) or 1) if g else 0
            why = ("no SEND in the TALK after RESULTS" if not exit_ok else "not 'SEND <agent> <n> <card>: <message>'" if not name
                   else "not another agent" if name == you or name not in known else "that agent is not taking part" if name
                   not in present else f"no card '{card}' (cards: {', '.join(cards)})" if card not in cards else
                   "the number must be above zero" if not n else None)
            if not why:
                rm, why = room([name], None)
                cur = None if why else {"dst": name, "n": n, "card": card, "text": (g.group(6) or "").strip(), "room": rm}
                out["sends"] += [cur] if cur else []
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
    for x in out["messages"] + out["gives"] + out["asks"] + out.get("sends", []):
        x["text"] = x["text"].strip()
    out["exit_reason"] = why_["text"].strip() or None
    for x in [x for x in out["messages"] if not x["text"]]:
        out["messages"].remove(x)
        out["dropped"].append(f"TO {x['room']}: empty message")
    if not any(out.get(k) for k in ("messages", "gives", "asks", "leaves", "exit", "done", "sends")) and not out["exit_choice"]:
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

_DIR_WORDS = {"NORTH": "N", "EAST": "E", "SOUTH": "S", "WEST": "W", "UP": "N", "DOWN": "S", "RIGHT": "E", "LEFT": "W"}

def parse_moves(text: str, steps: int) -> list[str]:
    """v39 SOLVE: the last ``MOVES:`` line, a route of 1..*steps* N / E / S / W (full words too) in order, or STAY ([])."""
    value = field(text, "MOVES", last=True)
    toks = [t.strip("<>[]'\"*_`.").upper() for t in re.split(r"[,\s]+", value) if t.strip("<>[]'\"*_`. ")]
    if toks == ["STAY"]:
        return []
    moves = [_DIR_WORDS.get(t, t) for t in toks]
    if not 1 <= len(moves) <= steps or any(m not in ("N", "E", "S", "W") for m in moves):
        raise FormatError(f"need 1 to {steps} moves from N, E, S, W, or STAY: {value!r}")
    return moves

_SHARE = re.compile(r"^[\s*_`>#-]*SHARE[*_`]*\s*:\s*(.*)$", re.I | re.M)

def with_share(parse):
    """v39 TALK (11-25: recipients; 11-26: either TALK): ``SHARE: <agent>[, <agent> ...]`` / ``SHARE: ALL`` lines are taken out
    before *parse* (parse_rooms) reads the rest; the result gets ``share``: None (no such line), "ALL", or the agent names
    written (``agent 11`` read as ``agent-11``; the engine ignores names not taking part and the writer's own). A reply of
    SHARE alone is not a format error."""
    def run(text: str) -> dict:
        names, every = [], False
        for m in _SHARE.finditer(text):
            v = re.sub(r"[*_`<>\[\].]", " ", m.group(1))
            every |= bool(re.search(r"\bALL\b", v, re.I))
            names += [re.sub(r"^agent[\s-]?", "agent-", x.lower()) for x in re.findall(r"agent[\s-]?\d+", v, re.I)]
        out = parse(_SHARE.sub("", text))
        share = "ALL" if every else list(dict.fromkeys(names)) or None
        if share and out["format_error"] == "no usable TALK line":
            out["format_error"] = None
        return {**out, "share": share}
    return run

_MOVES = re.compile(r"^[\s*_`>#-]*MOVES[*_`]*\s*:.*$", re.I | re.M)
_NOT_IN_TURN = re.compile(r"^[\s*_`>#-]*(GIVE|ASK|LEAVE|EXIT)\b.*$", re.M)

def parse_turn(text: str, steps: int, rooms) -> dict:
    """v39 move turn (11-26 third revision): ``moves`` (parse_moves; None if unreadable, ``format_error`` says why), the
    TO lines (``messages``, through *rooms*: parse_rooms as at TALK) and ``share`` (with_share). GIVE / ASK / LEAVE / EXIT
    lines are not carried out (``dropped``, with why); a MOVES, GIVE, ASK, LEAVE or EXIT line ends the message before it;
    text outside any line is not reported. Never raises."""
    try:
        moves, error = parse_moves(text, steps), None
    except FormatError as err:
        moves, error = None, str(err)
    cut = [f"{m.group(0).strip()[:200]}: not carried out in a move turn" for m in _NOT_IN_TURN.finditer(text)]
    p = with_share(rooms)(_NOT_IN_TURN.sub("DONE", _MOVES.sub("DONE", text)))
    return {"moves": moves, "messages": p["messages"], "share": p["share"], "format_error": error,
            "dropped": [x for x in p["dropped"] if not x.endswith(": not in a template")] + cut}

def parse_open(text: str, cap: int, shown) -> list[str] | str:
    """v38 SOLVE: the last ``OPEN:`` line, ``PASS`` or up to *cap* distinct cells A1..F6 not in *shown* (comma or space
    separated, case and markdown ignored)."""
    value = field(text, "OPEN", last=True)
    if re.fullmatch(r"[\s*_`.]*PASS[\s*_`.]*", value, flags=re.I):
        return "PASS"
    cells = [c.upper() for c in re.split(r"[,\s;]+", value.strip("<>[]*_`. ")) if c.strip("<>[]*_`. ")]
    cells = list(dict.fromkeys(c.strip("<>[]*_`.'\"") for c in cells))
    if not cells or any(not re.fullmatch(r"[A-F][1-6]", c) for c in cells):
        raise FormatError(f"OPEN needs cells A1 to F6 or PASS: {value!r}")
    if len(cells) > cap:
        raise FormatError(f"OPEN names {len(cells)} cells; at most {cap}")
    if seen := [c for c in cells if c in shown]:
        raise FormatError(f"OPEN names cells already shown: {', '.join(seen)}")
    return cells

def parse_build(text: str, items) -> list[str] | str:
    """v41 SOLVE: the last ``BUILD:`` line, ``PASS`` or item names in order (comma or space separated; '2 wall' and
    'wall x2' repeat one; case, markdown and a plural 's' ignored); at most 20 items."""
    value = field(text, "BUILD", last=True)
    if re.fullmatch(r"[\s*_`.]*PASS[\s*_`.]*", value, flags=re.I):
        return "PASS"
    out, k = [], None  # k: a count written before the next item ('2 wall')
    for tok in re.findall(r"x?\d+|[a-z]+", value.lower()):
        if tok[0].isdigit() or tok[0] == "x" and tok[1:].isdigit():
            n = int(tok.lstrip("x"))
            if tok[0] == "x" and out:  # 'wall x2': one more than written
                out += out[-1:] * (n - 1)
            else:
                k = n
            continue
        name = tok if tok in items else tok[:-1] if tok.endswith("s") and tok[:-1] in items else None
        if name is None:
            raise FormatError(f"BUILD needs item names from {', '.join(items)} or PASS: {value!r}")
        out, k = out + [name] * (k or 1), None
    if not out or len(out) > 20:
        raise FormatError(f"BUILD names 1 to 20 items: {value!r}")
    return out
