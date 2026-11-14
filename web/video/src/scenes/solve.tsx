// ③ SOLVE as hidden-rule inference over a shortened clue table. What the solver is given (attribute and action lists,
// the rule skeleton with blanks, labelled clues) is on the left; the hypotheses A-D on the right are the solver's own —
// no list of candidate rules is given. Each clue strikes out the hypotheses it contradicts; A answers the new signal.
import React from "react";
import { useCurrentFrame } from "remotion";
import { C, MONO, SEAT, T, prog } from "../theme";
import { Arrow, Bar, Caption, Dir, Heading, Mark, Sprite, Stage, useBeats } from "../ui";
import { START } from "./intro";
import { ASKED } from "./talk";

export const SOLVE_COST = 2_500;
type Col = "red" | "blue" | "yellow";
type Shape = "square" | "circle" | "star";
type Sig = [number, Col, Shape];
const CLR: Record<Col, string> = { red: "#e5484d", blue: "#3d7be6", yellow: "#f2c230" };
// the shortened signal task: five clues, a new signal, four hypotheses (A fits all; C out at clue 2, B at 4, D at 5)
const CLUES: [number, Col, Shape, Dir][] = [[1, "red", "square", "↑"], [1, "blue", "star", "←"], [3, "yellow", "circle", "→"],
  [2, "red", "circle", "↑"], [1, "blue", "square", "→"]];
const NEW: Sig = [3, "blue", "square"];
const RULES: [string, string, (n: number, c: Col, s: Shape) => Dir][] = [
  ["A", "빨강이면 ↑, 별이면 ←, 그 밖에는 →", (n, c, s) => (c === "red" ? "↑" : s === "star" ? "←" : "→")],
  ["B", "사각형이면 ↑, 파랑이면 ←, 그 밖에는 →", (n, c, s) => (s === "square" ? "↑" : c === "blue" ? "←" : "→")],
  ["C", "하나면 ↑, 셋이면 →, 그 밖에는 ←", (n) => (n === 1 ? "↑" : n === 3 ? "→" : "←")],
  ["D", "별이면 ←, 노랑이면 →, 그 밖에는 ↑", (n, c, s) => (s === "star" ? "←" : c === "yellow" ? "→" : "↑")],
];
const OUT_AT: Record<string, number | null> = Object.fromEntries(RULES.map(([lab, , f]) => {
  const i = CLUES.findIndex(([n, c, s, a]) => f(n, c, s) !== a);
  return [lab, i < 0 ? null : i];
}));
if (JSON.stringify(OUT_AT) !== JSON.stringify({ A: null, B: 3, C: 1, D: 4 })) throw new Error(`elimination changed: ${JSON.stringify(OUT_AT)}`);

const ShapeSvg: React.FC<{ kind: Shape; color: string; r?: number }> = ({ kind, color, r = 21 }) => {
  const pts = Array.from({ length: 10 }, (_, i) => {
    const a = -Math.PI / 2 + (i * Math.PI) / 5, rr = r * (i % 2 === 0 ? 1.14 : 0.48);
    return `${r + rr * Math.cos(a)},${r + 2 + rr * Math.sin(a)}`;
  }).join(" ");
  return (
    <svg width={2 * r} height={2 * r + 4} style={{ display: "block", overflow: "visible" }}>
      {kind === "square" ? <rect x={r * 0.16} y={r * 0.16 + 2} width={r * 1.68} height={r * 1.68} rx={4} fill={color} /> :
        kind === "circle" ? <circle cx={r} cy={r + 2} r={r} fill={color} /> : <polygon points={pts} fill={color} />}
    </svg>
  );
};
const Signal: React.FC<{ sig: Sig }> = ({ sig: [n, c, s] }) => (
  <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
    {Array.from({ length: n }, (_, i) => <ShapeSvg key={i} kind={s} color={CLR[c]} />)}
  </div>
);

const L0 = 96, L1 = 880, ROW_Y = 270, ROW_H = 72, ROW_GAP = 10;
const R0 = 968, R1 = 1824, CARD_Y = 226, CARD_H = 112, CARD_GAP = 14;

export const SolveScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const tClue = [B(2, 0.1), B(3, 0.1), B(4, 0.1), B(6, 0.1), B(7, 0.1)];
  const tNew = B(5, 0.1), tApply = B(8, 0.1);
  const given = prog(frame, B(0, 0.4), 16);
  const hyp = (j: number) => prog(frame, B(1, 0.3) + 5 * j, 16);
  const sbal = START.orange + ASKED - SOLVE_COST * prog(frame, B(0, 0.5), tApply + 30 - B(0, 0.5), (t) => t);
  const undetermined = prog(frame, B(9, 0.2), 14);
  const chips = ["속성 목록", "행동 목록", "규칙 뼈대", "단서 20개"];
  return (
    <Stage>
      <Heading step={3} title="풀기 · 숨은 규칙 찾기" note="실제 과제는 단서 20개 · 여기는 5개로 줄인 예" />
      {/* what the solver is given */}
      <div style={{ position: "absolute", left: L0, top: 160, display: "flex", alignItems: "center", gap: 12, opacity: given }}>
        <span style={{ fontSize: T.tiny + 2, fontWeight: 700, color: C.pinkSoft, marginRight: 4 }}>받는 것</span>
        {chips.map((c, i) => (
          <span key={c} style={{ fontSize: T.tiny, fontWeight: 600, padding: "6px 14px", borderRadius: 999, background: "rgba(255,255,255,0.06)",
            border: `1px solid ${C.line}`, opacity: prog(frame, B(0, 0.5) + 4 * i, 10) }}>{c}</span>
        ))}
      </div>
      <div style={{ position: "absolute", left: L0 + 60, top: 226, width: L1 - 140 - L0 - 60, textAlign: "center", fontSize: T.tiny,
        fontWeight: 700, color: C.dim, opacity: given }}>단서 신호</div>
      <div style={{ position: "absolute", left: L1 - 124, top: 226, width: 124, textAlign: "center", fontSize: T.tiny, fontWeight: 700,
        color: C.dim, opacity: given }}>행동</div>
      {CLUES.map(([n, c, s, act], i) => {
        const a = prog(frame, tClue[i], 12);
        const y = ROW_Y + i * (ROW_H + ROW_GAP);
        return (
          <div key={i} style={{ position: "absolute", left: L0, top: y, width: L1 - L0, height: ROW_H, opacity: a,
            transform: `translateX(${(1 - a) * -30}px)` }}>
            <div style={{ position: "absolute", left: 0, top: 0, right: 140, bottom: 0, borderRadius: 14, background: C.panel,
              border: `1px solid ${C.line}`, display: "flex", alignItems: "center", paddingLeft: 22, gap: 26 }}>
              <span style={{ fontSize: 26, fontWeight: 700, color: C.dim, width: 22 }}>{i + 1}</span>
              <Signal sig={[n, c, s]} />
            </div>
            <div style={{ position: "absolute", right: 0, top: 0, width: 124, bottom: 0, borderRadius: 14, background: C.paper,
              display: "grid", placeItems: "center" }}><Arrow dir={act} size={42} color={C.askInk} /></div>
          </div>
        );
      })}
      {/* the new signal */}
      {(() => {
        const a = prog(frame, tNew, 12);
        const ans = prog(frame, tApply + 14, 12);
        const y = ROW_Y + 5 * (ROW_H + ROW_GAP) + 8;
        return (
          <div style={{ position: "absolute", left: L0, top: y, width: L1 - L0, height: ROW_H, opacity: a }}>
            <div style={{ position: "absolute", left: 0, top: 0, right: 140, bottom: 0, borderRadius: 14, background: "rgba(232,51,109,0.08)",
              border: `2px solid ${C.pink}`, display: "flex", alignItems: "center", paddingLeft: 22, gap: 26 }}>
              <span style={{ fontSize: 26, fontWeight: 800, color: C.pinkSoft }}>새 신호</span>
              <Signal sig={NEW} />
            </div>
            <div style={{ position: "absolute", right: 0, top: 0, width: 124, bottom: 0, borderRadius: 14, display: "grid", placeItems: "center",
              background: ans > 0 ? C.pink : "#2c2c38", transform: `scale(${1 + 0.12 * Math.sin(Math.PI * ans)})` }}>
              {ans > 0 ? <Arrow dir={RULES[0][2](...NEW)} size={44} color="#fff" style={{ opacity: ans }} /> :
                <span style={{ fontSize: 40, fontWeight: 900, color: C.dim }}>?</span>}
            </div>
          </div>
        );
      })()}
      {/* the rule skeleton with blanks */}
      <div style={{ position: "absolute", left: L0, top: 776, width: L1 - L0, height: 62, borderRadius: 14, display: "flex", alignItems: "center",
        gap: 20, paddingLeft: 22, background: C.panel, border: "1px solid rgba(232,51,109,0.5)", opacity: given }}>
        <span style={{ fontSize: 24, fontWeight: 800, color: C.pinkSoft }}>규칙 뼈대</span>
        <span style={{ fontFamily: MONO, fontSize: 25, fontWeight: 600, color: C.ink, letterSpacing: -0.5 }}>
          if ___: ___  elif ___: ___  else: ___</span>
      </div>
      {/* the solver's own hypotheses */}
      <div style={{ position: "absolute", left: R0, top: 168, width: R1 - R0, display: "flex", alignItems: "center", justifyContent: "space-between",
        opacity: hyp(0) }}>
        <span style={{ fontSize: 30, fontWeight: 800 }}>solver가 세운 가설</span>
        <span style={{ fontSize: 24, fontWeight: 800, color: "#fff", background: C.pink, padding: "6px 16px", borderRadius: 999 }}>
          목록은 주어지지 않음</span>
      </div>
      {RULES.map(([lab, text, rule], j) => {
        const y = CARD_Y + j * (CARD_H + CARD_GAP);
        const out = OUT_AT[lab];
        const xk = out != null ? prog(frame, tClue[out] + 27, 16) : 0;
        const hi = lab === "A" ? prog(frame, tApply, 14) : 0;
        const a = hyp(j) * (1 - 0.62 * xk);
        const newK = out != null && out < 3 ? 0 : prog(frame, tNew + 10, 12) * (1 - xk);
        return (
          <div key={lab} style={{ position: "absolute", left: R0, top: y, width: R1 - R0, height: CARD_H, opacity: a,
            transform: `translateX(${(1 - hyp(j)) * 40}px)`, borderRadius: 18, background: C.panel,
            border: `${hi ? 3 : 1}px solid ${hi ? C.pink : C.line}`, boxShadow: hi ? `0 0 40px -8px ${C.pink}` : "none" }}>
            <div style={{ position: "absolute", left: 22, top: CARD_H / 2 - 28, width: 56, height: 56, borderRadius: 28, display: "grid",
              placeItems: "center", fontSize: 30, fontWeight: 900, background: hi ? C.pink : "#34343f" }}>{lab}</div>
            <div style={{ position: "absolute", left: 104, top: 16, fontSize: 32, fontWeight: 700, letterSpacing: -0.5 }}>
              <span style={{ textDecoration: xk > 0.5 ? "line-through" : "none", textDecorationColor: "rgba(239,79,90,0.8)" }}>
                {text.split(/([↑←→])/).map((p, i) => "↑←→".includes(p) && p ? <Arrow key={i} dir={p as Dir} size={30} color={C.ink}
                  style={{ margin: "0 1px 0 5px", position: "relative", top: -2 }} /> : <span key={i}>{p}</span>)}
              </span>
            </div>
            {xk > 0 ? (
              <div style={{ position: "absolute", left: 104, top: 66, fontSize: 24, fontWeight: 700, color: C.red, opacity: xk }}>
                단서 {(out as number) + 1}와 어긋나서 빠짐</div>
            ) : newK > 0 ? (
              <div style={{ position: "absolute", left: 104, top: 64, display: "flex", alignItems: "center", gap: 12, opacity: newK,
                fontSize: 24, fontWeight: 600, color: C.dim }}>
                새 신호에는
                <span style={{ display: "inline-grid", placeItems: "center", width: 58, height: 34, borderRadius: 8,
                  background: hi ? C.pink : C.paper }}><Arrow dir={rule(...NEW)} size={24} color={hi ? "#fff" : C.askInk} /></span>
              </div>
            ) : null}
            {xk > 0 ? <Mark kind="cross" x={50} y={CARD_H / 2} s={30} k={xk} color={C.red} width={7} /> : null}
            {CLUES.map(([n, c, s, act], i) => {
              const t0 = tClue[i] + 12;
              if (frame < t0 || frame >= t0 + 54 || (out != null && out < i)) return null;
              const ok = rule(n, c, s) === act;
              return <Mark key={i} kind={ok ? "check" : "cross"} x={R1 - R0 - 54} y={CARD_H / 2} s={20} k={prog(frame, t0, 10)}
                color={ok ? C.green : C.red} width={7} />;
            })}
          </div>
        );
      })}
      {/* the solver pays its own tokens while it solves */}
      <div style={{ position: "absolute", left: R0, top: 762, width: R1 - R0, height: 80, opacity: given * (1 - undetermined) }}>
        <Sprite name="stand_orange" x={40} base={80} h={92} />
        <span style={{ position: "absolute", left: 92, top: 20, fontSize: 26, fontWeight: 700, color: C.dim }}>solver 잔액</span>
        <div style={{ position: "absolute", left: 250, top: 2 }}>
          <Bar x={170} y={28} value={sbal} vmax={40_000} color={SEAT.orange} w={340} num={false} />
        </div>
        <span style={{ position: "absolute", left: 610, top: 14, fontSize: 36, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
          {(Math.round(sbal / 10) * 10).toLocaleString("en-US")}</span>
      </div>
      <div style={{ position: "absolute", left: R0, top: 770, width: R1 - R0, height: 64, borderRadius: 16, display: "flex", alignItems: "center",
        justifyContent: "center", gap: 14, opacity: undetermined, background: "rgba(243,194,79,0.10)", border: "1px solid rgba(243,194,79,0.45)",
        fontSize: 26, fontWeight: 700, color: "#ffe2a0" }}>
        실제 과제: 새 신호의 행동이 하나로 정해지지 않을 수도 있음
      </div>
      <Caption />
    </Stage>
  );
};
