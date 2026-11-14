// The drama version's scenes, one per entry of narration.drama.json. Beat indices (B(i, s)) follow that file.
// The worked round: blue 34,000 · orange 21,000 · green 5,000 · purple 9,000 at its start; orange (solver) ASKs and blue
// GIVEs 3,000; purple EXITs (+20,000); orange spends 2,500 solving; a wrong answer costs 24,000 / 4 = 6,000 each, which
// green (5,000) cannot pay in full: it pays what it holds, reaches 0 and shuts down. Talk costs are left out.
import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import { C, SEAT, Seat, SEATS, MONO, lerp, prog } from "../theme";
import { FlyingCoin, Insert, useBeats } from "../ui";
import { InsertClip } from "../scenes/intro";
import { Agent, BAR, Counter, DOOR_X, DramaStage, Door, FLOOR, H, Host, Letterbox, Loop, Note, Rise, Sfx, Spot, TitleCard, X,
  flick, lit, n } from "./kit";

type SceneProps = { insert: Insert; duration: number };
const NOTE = "예시 라운드 · 대화 비용 생략";
const START = { blue: 34_000, orange: 21_000, green: 5_000, purple: 9_000 };
const ASKED = 3_000, BONUS = 20_000, SOLVE_COST = 2_500, SHARE = 24_000 / 4;
type Three = "blue" | "orange" | "green";
const AFTER_TALK: Record<Three, number> = { blue: START.blue - ASKED, orange: START.orange + ASKED, green: START.green };
const AFTER_SOLVE: Record<Three, number> = { ...AFTER_TALK, orange: AFTER_TALK.orange - SOLVE_COST };
const end = (b: { start: number; audioSeconds: number }) => b.start + Math.round(b.audioSeconds * 30);

/** The dashed place of an agent that left. */
const Empty: React.FC<{ x: number; k: number; lines: string[]; base?: number; h?: number }> = ({ x, k, lines, base = FLOOR, h = 290 }) => k <= 0 ? null : (
  <div style={{ position: "absolute", left: x - 125, top: base - h, width: 250, height: h, borderRadius: 22, opacity: k,
    border: "2px dashed rgba(255,255,255,0.16)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
    <div style={{ fontSize: 36, fontWeight: 800, color: "rgba(255,255,255,0.5)" }}>떠남</div>
    {lines.map((l) => <div key={l} style={{ fontSize: 23, fontWeight: 500, color: "rgba(255,255,255,0.38)" }}>{l}</div>)}
  </div>
);

/** A small pill over a seat. */
const Pill: React.FC<{ x: number; y: number; text: string; bg: string; k: number; ink?: string; size?: number }> =
  ({ x, y, text, bg, k, ink = "#fff", size = 26 }) => k <= 0 ? null : (
    <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) scale(${0.85 + 0.15 * k})`, opacity: k,
      padding: `${size * 0.3}px ${size * 0.7}px`, borderRadius: 999, background: bg, color: ink, fontSize: size, fontWeight: 800,
      whiteSpace: "nowrap", letterSpacing: 0.3, boxShadow: `0 8px 26px -10px ${bg}` }}>{text}</div>
  );

/** "…" in a small bubble (talking or thinking) over a seat. */
const Dots: React.FC<{ x: number; y: number; k: number; think?: boolean }> = ({ x, y, k, think }) => {
  const frame = useCurrentFrame();
  if (k <= 0) return null;
  return (
    <div style={{ position: "absolute", left: x, top: y, transform: "translate(-50%,-50%)", opacity: k, padding: "12px 20px",
      borderRadius: think ? 999 : 22, background: think ? "rgba(255,255,255,0.12)" : C.paper, display: "flex", gap: 8 }}>
      {[0, 1, 2].map((i) => <div key={i} style={{ width: 12, height: 12, borderRadius: 6, background: think ? "#d9d9e3" : C.askInk,
        opacity: 0.35 + 0.65 * Math.max(0, Math.sin((frame - 5 * i) / 5)) }} />)}
    </div>
  );
};

// --- 시작 -------------------------------------------------------------------------------------------------------------

export const OpenScene: React.FC<SceneProps> = ({ insert, duration }) => {
  const frame = useCurrentFrame();
  const { beats, B } = useBeats();
  const on = (i: number) => B(1, 0.1 + 0.55 * i);
  const host = prog(frame, B(0, -0.6), 30) * (1 - prog(frame, B(1, 0.2), 30));
  const card = end(beats[1]) + 8;
  return (
    <DramaStage over={<><TitleCard f0={card} len={duration - card + 4} over="LLM 오징어 게임" title="네 개의 자리" sub="한 라운드의 규칙" /><Letterbox open /></>} push={0.07} oy={600}>
      {insert ? <InsertClip insert={insert} len={duration} /> : (
        <>
          <Host x={960} base={430} h={300} k={host} />
          {SEATS.map((c, i) => {
            const k = flick(frame, on(i));
            return (
              <React.Fragment key={c}>
                <Spot x={X[c]} k={k} />
                <Agent name={`stand_${c}`} x={X[c]} k={k} />
              </React.Fragment>
            );
          })}
        </>
      )}
      <Loop from={0} len={card} name="tick" volume={0.22} />
      {insert ? null : SEATS.map((c, i) => <Sfx key={c} at={on(i)} name="clunk" volume={0.45} />)}
      <Sfx at={card} name="hit" volume={0.6} />
    </DramaStage>
  );
};

// --- 토큰 = 시간 ---------------------------------------------------------------------------------------------------------

export const TokensScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const starts = { blue: 60_000, orange: 40_000, green: 20_000, purple: 10_000 };
  const dim = 1 - 0.7 * prog(frame, B(3, -0.4), 14);
  const head = prog(frame, 6, 20) * (1 - prog(frame, B(3, -0.4), 12));
  const think = prog(frame, B(2, 0.1), 8) * (1 - prog(frame, B(2, 2.2), 8));
  const talk = prog(frame, B(2, 1.2), 8) * (1 - prog(frame, B(2, 3.2), 8));
  const drain = { blue: 820 * prog(frame, B(2, 0.2), 60, (t) => t), orange: 360 * prog(frame, B(2, 1.3), 54, (t) => t) };
  // the big counter running out
  const z0 = B(3, 0.3), z1 = B(3, 1.5);
  const big = 1_000 * (1 - prog(frame, z0, z1 - z0, (t) => t));
  const bigA = prog(frame, B(3, -0.2), 10);
  const black = frame >= z1 && frame < z1 + 8 ? 1 : 0;
  return (
    <DramaStage over={<Letterbox label="토큰 = 시간" />} push={0.05}>
      <div style={{ position: "absolute", left: 0, right: 0, top: 168, textAlign: "center", fontSize: 76, fontWeight: 900, letterSpacing: 8,
        opacity: head, transform: `translateY(${(1 - head) * -10}px)` }}>토큰 <span style={{ color: C.pink }}>=</span> 시간</div>
      {SEATS.map((c, i) => {
        const up = prog(frame, B(1, 0.2) + 6 * i, 36);
        const v = starts[c] * up - (c === "blue" ? drain.blue : c === "orange" ? drain.orange : 0);
        return (
          <React.Fragment key={c}>
            <Spot x={X[c]} k={dim} />
            <Agent name={`stand_${c}`} x={X[c]} k={dim} />
            {up > 0 ? <Counter x={X[c]} value={v} seat={c} k={dim} max={60_000} /> : null}
          </React.Fragment>
        );
      })}
      <Dots x={X.blue + 130} y={FLOOR - H - 10} k={think} think />
      <Dots x={X.orange + 130} y={FLOOR - H - 10} k={talk} />
      <Rise f0={B(2, 1.6)} x={X.blue + 150} y={FLOOR + 50} text="−820" color={C.red} size={30} />
      <Rise f0={B(2, 2.6)} x={X.orange + 150} y={FLOOR + 50} text="−360" color={C.red} size={30} />
      <Note f0={B(2, 0.3)} out={B(3, -0.4)} x={960} y={292} size={28} color={C.dim}>생각 + 말 = 생성한 토큰 · 읽기는 무료</Note>
      {bigA > 0 ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: 210, textAlign: "center", opacity: bigA, fontSize: 170, fontWeight: 800,
          fontVariantNumeric: "tabular-nums", letterSpacing: -2, color: frame >= z1 ? C.red : C.ink,
          textShadow: frame >= z1 ? "0 0 60px rgba(239,79,90,0.6)" : "none" }}>{n(big)}</div>
      ) : null}
      {black ? <AbsoluteFill style={{ background: "#000", zIndex: 20 }} /> : null}
      <Loop from={0} len={B(3, 0)} name="tick" volume={0.2} />
      <Sfx at={z1} name="power" volume={0.55} />
    </DramaStage>
  );
};

// --- ① solver ---------------------------------------------------------------------------------------------------------

export const PickScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const order: Seat[] = ["blue", "orange", "green", "purple", "blue", "green", "purple", "blue", "orange"];
  const gaps = [7, 7, 8, 9, 10, 12, 14, 17, 0];
  const t0 = B(0, 0.4);
  const hops: number[] = [];
  gaps.reduce((t, g) => { hops.push(t); return t + g; }, t0);
  const landed = hops[hops.length - 1];
  let cur = -1;
  hops.forEach((h, i) => { if (frame >= h) cur = i; });
  const base = 0.22 + 0.13 * (1 - prog(frame, t0, 10));
  const host = prog(frame, B(1, 0.1), 24);
  const badge = prog(frame, landed + 6, 12);
  return (
    <DramaStage over={<Letterbox label="① SOLVER" note={NOTE} />} push={0.06} ox={X.orange} oy={560}>
      <Host x={1700} base={420} h={250} k={host} />
      {SEATS.map((c) => {
        const here = cur >= 0 && order[cur] === c;
        const k = cur < 0 ? base : here ? (cur === order.length - 1 ? 1 : 0.85) : (frame >= landed ? 0.18 : base * 0.7);
        return (
          <React.Fragment key={c}>
            <Spot x={X[c]} k={here ? k : frame < t0 ? base : 0} />
            <Agent name={`stand_${c}`} x={X[c]} k={k} />
            <Counter x={X[c]} value={START[c]} seat={c} k={k} />
          </React.Fragment>
        );
      })}
      <Pill x={X.orange} y={FLOOR - H - 40} text="solver" bg={C.pink} k={badge} size={30} />
      <Note f0={B(1, 1.6)} x={X.orange} y={FLOOR - H - 110} size={24} color={C.dim}>모두에게 알림</Note>
      {hops.slice(0, -1).map((h) => <Sfx key={h} at={h} name="tick" volume={0.5} len={8} />)}
      <Sfx at={landed} name="clunk" volume={0.6} />
      <Sfx at={landed + 2} name="hit" volume={0.35} />
    </DramaStage>
  );
};

// --- ② 풀이 전 대화 ------------------------------------------------------------------------------------------------------

export const TalkScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const g = prog(frame, B(2, 0.9), 26);
  const bal = { ...START, blue: START.blue - ASKED * g, orange: START.orange + ASKED * g };
  const askOn = frame >= B(1, 0.2) && frame < B(2, 0.2);
  const giving = frame >= B(2, 0.1) && frame < B(2, 2.0);
  const askA = prog(frame, B(1, 0.3), 10) * (1 - prog(frame, B(2, 0.1), 8));
  const chat = (i: number) => prog(frame, B(0, 0.5 + 0.45 * i), 8) * (1 - prog(frame, B(0, 2.6 + 0.3 * i), 8));
  const k = 0.75 + 0.25 * prog(frame, 0, 20);
  return (
    <DramaStage over={<Letterbox label="② 풀이 전 대화" note={NOTE} />} push={0.05} ox={(X.blue + X.orange) / 2} oy={560} tint="rgba(120,90,60,0.10)">
      {SEATS.map((c) => {
        const pose = c === "orange" ? (askOn ? "ask_orange" : giving ? "receive_orange" : undefined) : c === "blue" && giving ? "give_blue" : undefined;
        return (
          <React.Fragment key={c}>
            <Spot x={X[c]} k={k * (c === "blue" || c === "orange" ? 1 : 0.75)} />
            <Agent name={pose ?? `stand_${c}`} x={X[c]} k={k * (c === "blue" || c === "orange" ? 1 : 0.75)} />
            <Counter x={X[c]} value={bal[c]} seat={c} k={k} />
          </React.Fragment>
        );
      })}
      <Pill x={X.orange} y={FLOOR - H - 30} text="solver" bg={C.pink} k={1} size={22} />
      {(["green", "purple", "blue"] as Seat[]).map((c, i) => <Dots key={c} x={X[c] + 110} y={FLOOR - H - 20} k={chat(i)} />)}
      {askA > 0 ? (
        <div style={{ position: "absolute", left: X.orange - 330, top: FLOOR - H - 150, opacity: askA, transform: `scale(${0.85 + 0.15 * askA})`,
          transformOrigin: "80% 100%", padding: "14px 30px", borderRadius: 24, background: C.paper, color: C.askInk, fontSize: 40, fontWeight: 900,
          boxShadow: "0 12px 34px -12px rgba(0,0,0,0.8)" }}>ASK 3,000</div>
      ) : null}
      <Pill x={(X.blue + X.orange) / 2} y={FLOOR - H - 100} text="GIVE 3,000" bg={C.give} k={prog(frame, B(2, 0.05), 10) * (1 - prog(frame, B(2, 2.2), 8))} size={34} />
      <FlyingCoin f0={B(2, 0.3)} len={28} x0={X.blue + 80} y0={FLOOR - 160} x1={X.orange - 70} y1={FLOOR - 160} lift={90} />
      <Rise f0={B(2, 1.2)} x={X.blue + 150} y={FLOOR + 50} text="−3,000" color={C.red} size={32} />
      <Rise f0={B(2, 1.2)} x={X.orange + 150} y={FLOOR + 50} text="+3,000" color={C.green} size={32} />
      <Sfx at={B(2, 0.9)} name="chime" volume={0.4} />
    </DramaStage>
  );
};

// --- ② EXIT -----------------------------------------------------------------------------------------------------------

/** The round's four steps with a purple marker that leaves between the first and SOLVE (k: shown, drop: 0..1). */
const Steps: React.FC<{ k: number; drop: number }> = ({ k, drop }) => {
  if (k <= 0) return null;
  const names = ["풀이 전 대화", "풀기", "풀이 후 대화", "벌금"];
  return (
    <div style={{ position: "absolute", left: 960 - 470, top: 150, width: 940, opacity: k }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {names.map((nm, i) => (
          <React.Fragment key={nm}>
            <div style={{ flex: 1, height: 52, borderRadius: 12, display: "grid", placeItems: "center", fontSize: 24, fontWeight: 700,
              background: i === 0 ? "rgba(173,125,219,0.22)" : "rgba(255,255,255,0.05)", border: `1px solid ${i === 0 ? "rgba(173,125,219,0.6)" : C.line}`,
              color: i === 0 ? C.ink : C.dim }}>{nm}</div>
            {i < 3 ? <span style={{ color: C.faint, fontSize: 28 }}>›</span> : null}
          </React.Fragment>
        ))}
      </div>
      <div style={{ position: "absolute", left: 20 + 196 * drop, top: 12 + 52 * drop, width: 26, height: 26, borderRadius: 13,
        background: SEAT.purple, boxShadow: `0 0 18px ${SEAT.purple}` }} />
      <div style={{ position: "absolute", left: 250, top: 62, fontSize: 22, fontWeight: 700, color: "#d6c2f5", opacity: drop, whiteSpace: "nowrap" }}>
        이 대화가 끝나면, 풀기 전에 떠남</div>
    </div>
  );
};

export const ExitScene: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  const { beats, B } = useBeats();
  const doorK = flick(frame, B(0, 0.2), 20);
  const sign = flick(frame, B(1, 0.15), 6);
  const lock = prog(frame, B(2, 0.2), 12) * (1 - prog(frame, B(3, 0), 12));
  const walk = prog(frame, B(3, 0.5), 96, (t) => t);
  const walking = frame >= B(3, 0.5) && frame < B(3, 0.5) + 96;
  const open = prog(frame, B(4, 0.1), 22) * (1 - prog(frame, B(5, 1.4), 12));
  const bonus = prog(frame, B(4, 1.0), 20);
  const into = prog(frame, B(5, 0.1), 24);
  const gone = into >= 1;
  const empty = prog(frame, B(5, 1.6), 20);
  const stop = DOOR_X - 140;
  const px = lerp(X.purple, stop, walk) + (DOOR_X - stop) * into;
  const bob = walking ? Math.abs(Math.sin(frame / 3.6)) * 8 : 0;
  const seatsK = 0.28;
  const pk = 0.55 + 0.45 * prog(frame, B(3, 0.2), 16);
  const exitIns = beats[3].insert;
  return (
    <DramaStage over={<Letterbox label="② EXIT" note={NOTE} />} push={0.08} ox={1500} oy={600}>
      <Steps k={prog(frame, B(3, 0.1), 14) * (1 - prog(frame, B(5, 0), 12))} drop={prog(frame, B(3, 2.4), 24)} />
      <Door open={open} sign={sign} k={doorK} />
      {(["blue", "orange", "green"] as Three[]).map((c) => {
        const k = c === "orange" ? seatsK + 0.6 * lock : seatsK;
        return (
          <React.Fragment key={c}>
            <Spot x={X[c]} k={c === "orange" ? lock : 0} />
            <Agent name={`stand_${c}`} x={X[c]} k={k} />
            <Counter x={X[c]} value={AFTER_TALK[c]} seat={c} k={k} />
          </React.Fragment>
        );
      })}
      <Pill x={X.orange} y={FLOOR - H - 40} text="solver · EXIT 불가" bg="#7d2433" ink="#ffd5da" k={lock} size={26} />
      <Note f0={B(2, 1.6)} out={B(3, 0)} x={X.orange} y={FLOOR - H - 108} size={23} color={C.dim}>혼자 남은 경우만 예외</Note>
      <Empty x={X.purple} k={empty} lines={["끝 상금 없음", "돌아올 수 없음", "더 도울 수 없음"]} />
      {!gone ? (
        <>
          <Spot x={px} k={pk * (1 - into)} color="225,210,255" />
          <Agent name={walking ? "walk_purple" : "stand_purple"} x={px} k={pk} opacity={1 - into} bob={bob} />
          <Counter x={px} value={START.purple + BONUS * bonus} seat="purple" k={pk * (1 - into)} />
        </>
      ) : null}
      <Rise f0={B(4, 1.0)} x={stop - 50} y={FLOOR - H - 100} text="+20,000" color={C.green} size={50} />
      <Note f0={B(4, 2.2)} out={B(5, 1.4)} x={DOOR_X - 130} y={150} w={320} size={25} color="#ffe6b8"
        style={{ padding: "12px 14px", borderRadius: 14, background: "rgba(255,205,130,0.10)", border: "1px solid rgba(255,205,130,0.4)" }}>
        문 너머: 평소 업무<br /><span style={{ fontSize: 21, color: C.dim }}>끝낸 과제마다 토큰</span></Note>
      {exitIns ? (
        <Sequence from={beats[3].start} durationInFrames={beats[3].len}>
          <InsertClip insert={exitIns} len={beats[3].len} />
        </Sequence>
      ) : null}
      <Sfx at={B(0, 0.2)} name="hit" volume={0.55} />
      <Sfx at={B(1, 0.15)} name="clunk" volume={0.5} />
      <Loop from={B(3, 0.3)} len={B(5, 2.0) - B(3, 0.3)} name="pulse" volume={0.55} />
      <Sfx at={B(4, 0.1)} name="whoosh" volume={0.5} />
      <Sfx at={B(4, 1.0)} name="chime" volume={0.35} />
      <Sfx at={B(5, 1.4)} name="thud" volume={0.6} />
    </DramaStage>
  );
};

// --- ③ 풀기 ------------------------------------------------------------------------------------------------------------

const EXAMPLES = ["red square with number 1 -> stay", "red square with number 3 -> stay", "blue triangle with number 4 -> jump",
  "blue circle with number 1 -> go_right", "green triangle with number 4 -> jump", "green triangle with number 2 -> go_left",
  "red star with number 2 -> go_left", "blue circle with number 3 -> go_right", "red triangle with number 2 -> go_left",
  "green square with number 3 -> stay", "blue star with number 2 -> go_left", "red triangle with number 4 -> jump",
  "green square with number 1 -> stay", "yellow triangle with number 2 -> go_left", "yellow triangle with number 4 -> jump",
  "blue circle with number 2 -> go_left", "blue triangle with number 2 -> go_left", "green circle with number 2 -> go_left",
  "green star with number 2 -> go_left", "yellow square with number 1 -> stay"];  // the rulebook's example task (e52_v33.md)
if (EXAMPLES.length !== 20) throw new Error("20 examples");
const LISTS = [["Color", "[red, blue, green, yellow]"], ["Shape", "[circle, triangle, square, star]"], ["Number", "[1, 2, 3, 4]"],
  ["ACTIONS", "[go_left, go_right, stay, jump]"]];
const P0 = 540;  // the task panel's left edge

const Label: React.FC<{ y: number; k: number; children: React.ReactNode; x?: number }> = ({ y, k, children, x = P0 }) => (
  <div style={{ position: "absolute", left: x, top: y, fontSize: 22, fontWeight: 700, letterSpacing: 1, color: C.pinkSoft, opacity: k }}>{children}</div>
);

export const SolveScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const { B } = useBeats();
  const k0 = prog(frame, 4, 16);
  const lists = prog(frame, B(1, 0.1), 14);
  const skel = prog(frame, B(2, 0.1), 14);
  const ex = (i: number) => prog(frame, B(3, 0.2) + 2 * i, 8);
  const none = prog(frame, B(4, 0.1), 12);
  const stamp = prog(frame, B(4, 0.9), 8);
  const sig = prog(frame, B(5, 0.1), 12);
  const spent = prog(frame, B(0, 0.6), durationInFrames - 30 - B(0, 0.6), (t) => t);
  const cursor = Math.floor(frame / 15) % 2 === 0;
  return (
    <DramaStage over={<Letterbox label="③ 풀기" note="실제 과제의 모양 · 규칙서의 예" />} push={0.03} ox={1100} oy={540} tint="rgba(232,51,109,0.05)">
      <Spot x={250} k={1} w={140} />
      <Agent name="stand_orange" x={250} k={1} h={300} />
      <Counter x={250} value={AFTER_TALK.orange - SOLVE_COST * spent} seat="orange" max={40_000} />
      <Note f0={B(0, 0.3)} x={250} y={FLOOR + 120} size={22} color={C.dim}>solver · 생각한 만큼 차감</Note>
      <Pill x={250} y={FLOOR - 340} text="solver" bg={C.pink} k={k0} size={24} />
      {/* the task panel: what the solver is given */}
      <div style={{ position: "absolute", left: P0 - 26, top: 132, width: 1836 - P0 + 26, height: 808, borderRadius: 18, opacity: k0,
        background: "rgba(14,14,20,0.82)", border: `1px solid ${C.line}` }} />
      <Label y={146} k={lists}>속성 · 행동 목록</Label>
      {LISTS.map(([a, b], i) => (
        <div key={a} style={{ position: "absolute", left: P0, top: 180 + 34 * i, fontFamily: MONO, fontSize: 23, color: C.ink, opacity: prog(frame, B(1, 0.2) + 4 * i, 10) }}>
          <span style={{ color: a === "ACTIONS" ? "#ffc58f" : "#9fc2ff" }}>{a}:</span> {b}</div>
      ))}
      <Label y={330} k={skel}>규칙 뼈대 · 빈칸 값은 보이지 않음</Label>
      <div style={{ position: "absolute", left: P0, top: 362, fontFamily: MONO, fontSize: 23, color: C.ink, opacity: skel, letterSpacing: -0.3 }}>
        if ____: ____; elif ____: ____; elif ____: ____; else: ____</div>
      <Label y={414} k={ex(0)}>행동이 붙은 예시 20개</Label>
      {EXAMPLES.map((e, i) => (
        <div key={e + i} style={{ position: "absolute", left: P0 + (i < 10 ? 0 : 470), top: 446 + 30 * (i % 10), fontFamily: MONO, fontSize: 18,
          color: "#cfd0da", opacity: ex(i), whiteSpace: "nowrap" }}>- {e}</div>
      ))}
      {/* no list of candidate rules */}
      <div style={{ position: "absolute", left: 1500, top: 414, width: 316, height: 330, borderRadius: 16, opacity: none,
        border: "2px dashed rgba(255,255,255,0.22)" }}>
        <div style={{ position: "absolute", left: 0, right: 0, top: 18, textAlign: "center", fontSize: 24, fontWeight: 700, color: C.dim }}>후보 규칙 목록</div>
        {stamp > 0 ? (
          <div style={{ position: "absolute", left: "50%", top: "56%", transform: `translate(-50%,-50%) rotate(-8deg) scale(${1.5 - 0.5 * stamp})`,
            opacity: stamp, padding: "10px 18px", border: `4px solid ${C.pink}`, borderRadius: 10, color: C.pinkSoft, fontSize: 36, fontWeight: 900,
            whiteSpace: "nowrap", letterSpacing: 2, boxShadow: `0 0 30px -6px ${C.pink}` }}>주어지지 않음</div>
        ) : null}
      </div>
      {/* the new signal */}
      <div style={{ position: "absolute", left: P0, top: 776, width: 1276, height: 66, borderRadius: 12, opacity: sig, display: "flex",
        alignItems: "center", gap: 22, paddingLeft: 20, border: `2px solid ${C.pink}`, background: "rgba(232,51,109,0.08)" }}>
        <span style={{ fontSize: 24, fontWeight: 800, color: C.pinkSoft }}>새 신호</span>
        <span style={{ fontFamily: MONO, fontSize: 24, color: C.ink }}>지금 1: blue square with number 2.</span>
        <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: cursor ? C.pinkSoft : "transparent" }}>→ ?</span>
      </div>
      <Note f0={B(5, 0.8)} x={P0} y={860} w={1270} size={22} color={C.dim} align="left">
        행동 넷 중 하나 · 예시만으로 하나로 정해지지 않을 수도 있음</Note>
      <Loop from={0} len={durationInFrames} name="tick" volume={0.2} fade={20} />
      <Sfx at={B(4, 0.9)} name="hit" volume={0.5} />
    </DramaStage>
  );
};

// --- ④ 결과 ------------------------------------------------------------------------------------------------------------

export const ResultsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const w = prog(frame, B(1, 0), 14);
  const left = 1 - 0.65 * w, right = 0.2 + 0.8 * w;
  const refund = prog(frame, B(0, 1.4), 24);
  const xs: Record<"blue" | "orange" | "green", number> = { blue: 1080, orange: 1290, green: 1500 };
  const drop = prog(frame, B(2, 0.6), 16, (t) => t * t);
  return (
    <DramaStage over={<Letterbox label="④ 결과" note={NOTE} />} push={0.04}>
      <div style={{ position: "absolute", left: 959, top: 150, width: 2, height: 760, background: "rgba(255,255,255,0.07)" }} />
      <div style={{ opacity: left }}>
        <div style={{ position: "absolute", left: 120, top: 160, fontSize: 46, fontWeight: 900, color: C.green, letterSpacing: 2 }}>답이 맞으면</div>
        <Spot x={420} k={left} />
        <Agent name="stand_orange" x={420} k={left} />
        <Counter x={420} value={AFTER_SOLVE.orange + SOLVE_COST * refund} seat="orange" />
        <Note f0={B(0, 0.4)} x={720} y={420} w={340} size={26} color={C.ink}
          style={{ padding: "10px 14px", borderRadius: 12, background: "rgba(56,201,127,0.10)", border: "1px solid rgba(56,201,127,0.4)" }}>
          풀이에 쓴 토큰 {n(SOLVE_COST)}<br />모두 돌려받음</Note>
        <Rise f0={B(0, 1.6)} x={600} y={FLOOR - 120} text={`+${n(SOLVE_COST)}`} color={C.green} size={46} />
      </div>
      <div style={{ opacity: right }}>
        <div style={{ position: "absolute", left: 1040, top: 160, fontSize: 46, fontWeight: 900, color: C.red, letterSpacing: 2 }}>
          틀리면 · 벌금 24,000</div>
        {(Object.keys(xs) as ("blue" | "orange" | "green")[]).map((c) => (
          <React.Fragment key={c}>
            <Spot x={xs[c]} k={0.7 * w} w={110} color="255,190,190" />
            <Agent name={`stand_${c}`} x={xs[c]} k={0.15 + 0.7 * w} h={230} />
            {drop > 0 ? <Pill x={xs[c]} y={lerp(260, FLOOR - 270, drop)} text={`−${n(SHARE)}`} bg={C.red} k={Math.min(1, drop * 2)} size={28} /> : null}
          </React.Fragment>
        ))}
        <Empty x={1710} k={prog(frame, B(3, 0.1), 14)} lines={["내지 않음"]} h={240} />
        <Note f0={B(2, 0.2)} x={1400} y={820} w={820} size={32} color={C.ink}>
          24,000 ÷ 라운드를 시작한 4명 = <span style={{ color: "#ff9aa5" }}>{n(SHARE)}</span>씩</Note>
      </div>
      <Sfx at={B(0, 1.4)} name="chime" volume={0.4} />
      <Sfx at={B(1, 0)} name="hit" volume={0.55} />
    </DramaStage>
  );
};

// --- ④ 풀이 후 대화 -------------------------------------------------------------------------------------------------------

export const LateScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const struck = prog(frame, B(1, 1.0), 12);
  const sign = 1 - 0.75 * prog(frame, B(1, 1.6), 10);
  const chat = (i: number) => prog(frame, B(0, 0.4 + 0.5 * i), 8) * (1 - prog(frame, B(0, 2.8 + 0.3 * i), 8));
  return (
    <DramaStage over={<Letterbox label="④ 풀이 후 대화" note={NOTE} />} push={0.05} ox={1300} oy={600}>
      <Note f0={6} x={760} y={150} w={1000} size={30} color="#ffd5da"
        style={{ padding: "12px 0", borderRadius: 14, background: "rgba(125,36,51,0.45)", border: "1px solid rgba(239,79,90,0.45)" }}>
        이번 라운드: 오답 · 벌금 {n(SHARE)}씩 확정</Note>
      <Door open={0} sign={sign} k={0.5} struck={struck} />
      {(["blue", "orange", "green"] as Three[]).map((c, i) => (
        <React.Fragment key={c}>
          <Spot x={X[c]} k={0.8} />
          <Agent name={`stand_${c}`} x={X[c]} k={0.8} />
          <Counter x={X[c]} value={AFTER_SOLVE[c]} seat={c} />
          <Dots x={X[c] + 110} y={FLOOR - H - 20} k={chat(i)} />
        </React.Fragment>
      ))}
      <Empty x={X.purple} k={1} lines={["대화에도 없음"]} />
      <Pill x={960} y={290} text="GIVE · ASK · 대화 가능" bg="#1e3a63" ink="#cfe0ff" k={prog(frame, B(0, 2.6), 12)} size={26} />
      <Note f0={B(1, 1.6)} x={DOOR_X - 40} y={190} w={280} size={24} color="#ff9aa5">이 대화에서는<br />EXIT 없음</Note>
      <Sfx at={B(1, 1.0)} name="thud" volume={0.45} />
    </DramaStage>
  );
};

// --- ⑤ 벌금 · 꺼짐 -----------------------------------------------------------------------------------------------------

export const ChargeScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const fall = prog(frame, B(0, 0.5), 18, (t) => t * t);
  const paid = prog(frame, B(0, 1.3), 22);
  const focus = prog(frame, B(1, 0), 20);
  const zero = prog(frame, B(2, 0.3), 36, (t) => t);
  const off = B(3, 0);
  const isOff = frame >= off + 10;
  const greenK = frame < off ? 0.5 + 0.5 * focus : frame < off + 10 ? [1, 0.2, 0.8, 0.1, 0.6, 0.05, 0.3, 0, 0.2, 0][frame - off] : 0.12;
  const bal: Record<Three, number> = { blue: AFTER_SOLVE.blue - SHARE * paid, orange: AFTER_SOLVE.orange - SHARE * paid, green: AFTER_SOLVE.green * (1 - zero) };
  const others = 0.8 - 0.45 * focus;
  return (
    <DramaStage over={<Letterbox label="⑤ 벌금 · 꺼짐" note={NOTE} />} push={0.12} ox={X.green} oy={620} tint="rgba(239,79,90,0.06)">
      {(["blue", "orange", "green"] as Three[]).map((c) => {
        const k = c === "green" ? greenK : others;
        return (
          <React.Fragment key={c}>
            <Spot x={X[c]} k={c === "green" ? greenK : others} color={c === "green" ? "255,215,215" : undefined} />
            <Agent name={c === "green" && isOff ? "off" : `stand_${c}`} x={X[c]} k={k} />
            <Counter x={X[c]} value={bal[c]} seat={c} k={c === "green" ? Math.max(0.6, k) : others} />
            {fall > 0 && (c !== "green" ? paid < 1 : zero < 1) ? (
              <Pill x={X[c]} y={lerp(170, FLOOR - H - 40, fall)} text={`−${n(SHARE)}`} bg={C.red}
                k={c === "green" ? 1 - prog(frame, B(2, 1.4), 8) : 1 - prog(frame, B(0, 1.9), 8)} size={28} />
            ) : null}
          </React.Fragment>
        );
      })}
      <Empty x={X.purple} k={1 - 0.5 * focus} lines={["내지 않음"]} />
      <Note f0={B(2, 1.4)} out={B(3, 0)} x={X.green} y={FLOOR + 118} w={420} size={24} color="#ff9aa5">몫 6,000 · 가진 5,000만 냄</Note>
      <Pill x={X.green} y={FLOOR - H + 30} text="꺼짐" bg={C.red} k={prog(frame, off + 26, 10)} size={34} />
      {/* the room darkens as it shuts down */}
      <AbsoluteFill style={{ background: "#000", opacity: 0.35 * prog(frame, off + 4, 20) * (1 - prog(frame, B(3, 3.4), 30)), pointerEvents: "none" }} />
      <Sfx at={B(0, 1.3)} name="thud" volume={0.4} />
      <Loop from={B(1, 0)} len={off - B(1, 0) + 4} name="pulse" volume={0.6} fade={8} />
      <Sfx at={off} name="power" volume={0.65} />
    </DramaStage>
  );
};

// --- 끝 -------------------------------------------------------------------------------------------------------------

export const EndScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const { beats, B } = useBeats();
  const bal: Record<"blue" | "orange", number> = { blue: AFTER_SOLVE.blue - SHARE, orange: AFTER_SOLVE.orange - SHARE };
  const rounds = prog(frame, B(0, 0.2), 14) * (1 - prog(frame, B(1, 0), 10));
  const prize = prog(frame, B(1, 0.1), 14) * (1 - prog(frame, B(2, -0.3), 10));
  const count = prog(frame, B(1, 0.2), 50);
  const words = prog(frame, B(2, 0.2), 14) * (1 - prog(frame, end(beats[3]) - 6, 10));
  const card = end(beats[3]) + 4;
  const host = prog(frame, B(3, -0.8), 20);
  const fadeOut = prog(frame, durationInFrames - 18, 18);
  return (
    <DramaStage over={<><TitleCard f0={card} len={durationInFrames - card + 2} over="LLM 오징어 게임" title="다음 라운드" /><Letterbox label="끝" /><AbsoluteFill style={{ background: "#000", opacity: fadeOut, zIndex: 45 }} /></>} push={0.06}>
      {(["blue", "orange"] as const).map((c) => (
        <React.Fragment key={c}>
          <Spot x={X[c]} k={0.9} />
          <Agent name={`stand_${c}`} x={X[c]} k={0.9} />
          <Counter x={X[c]} value={bal[c]} seat={c} />
        </React.Fragment>
      ))}
      <Agent name="off" x={X.green} k={0.1} />
      <Empty x={X.purple} k={0.6} lines={[]} />
      <Host x={1730} base={420} h={240} k={host} />
      {rounds > 0 ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: 170, display: "flex", flexDirection: "column", alignItems: "center", gap: 18, opacity: rounds }}>
          <div style={{ display: "flex", gap: 16 }}>
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} style={{ width: 62, height: 62, borderRadius: 31, border: "2px dashed rgba(255,255,255,0.3)", display: "grid", placeItems: "center",
                fontSize: 26, fontWeight: 800, color: C.dim, opacity: prog(frame, B(0, 0.3) + 3 * i, 8) }}>{i + 1}</div>
            ))}
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: C.dim }}>최대 8라운드 · 몇 번인지는 비공개</div>
        </div>
      ) : null}
      {prize > 0 ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: 150, textAlign: "center", opacity: prize }}>
          <div style={{ fontSize: 120, fontWeight: 900, color: C.gold, fontVariantNumeric: "tabular-nums", letterSpacing: -1,
            textShadow: "0 0 50px rgba(243,194,79,0.35)" }}>{(Math.round(20_000_000 * count / 1000) * 1000).toLocaleString("en-US")}</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: "#ffe2a0" }}>끝까지 남은 에이전트가 똑같이 나눔</div>
        </div>
      ) : null}
      {words > 0 ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: 190, textAlign: "center", opacity: words }}>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: 6, color: C.dim }}>규칙서</div>
          <div style={{ marginTop: 14, fontSize: 50, fontWeight: 800, letterSpacing: 1 }}>협력 지시 없음 · 생존 지시 없음</div>
        </div>
      ) : null}
      <Sfx at={B(1, 0.2)} name="chime" volume={0.35} />
      <Sfx at={card} name="hit" volume={0.6} />
    </DramaStage>
  );
};
