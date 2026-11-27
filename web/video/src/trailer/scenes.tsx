// The trailer's sixteen scenes as sprite animation (figures of ./figure.tsx on the drama version's dark stage). Each
// scene is a component that reads its own frame (0 at the scene's first frame, 24 fps); what happens when follows
// docs/notes/2026-11-26-trailer-plan.md, section 6. A room is one mark: "claude" or "openai" on all its faces.
import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { C, FONT, SEAT, Seat, easeInOut, lerp, prog } from "../theme";
import { DramaStage, Spot, flick } from "../drama/kit";
import { Arm, Figure, GAUGE, HostFigure, Limb, Pose, armPoints, lift, pose, reach } from "./figure";
import type { Mark } from "./marks";
import { BAR, FLOOR, FPS, LINES, Line, T15_CUT, scene } from "./timing";

type P = [number, number];
const Svg: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <svg width={1920} height={1080} viewBox="0 0 1920 1080" style={{ position: "absolute", left: 0, top: 0, overflow: "visible", ...style }}>{children}</svg>
);
const io = (f: number, start: number, len: number) => prog(f, start, len, easeInOut);
const breathe = (f: number, phase = 0) => 0.85 + 0.05 * Math.sin((f / FPS) * (Math.PI / 2) + phase);   // the visor at rest: a 4 s cycle
const noise = (n: number) => { const v = Math.sin(n * 127.1 + 11.7) * 43758.5453; return v - Math.floor(v); };
/** A figure's local point on the frame. */
const at = (x: number, y: number, s: number, p: P): P => [x + p[0] * s, y + p[1] * s];

// --- the host at the table (T01, T02, T15) ---------------------------------------------------------------------------

/** The mask's three shapes while a line is spoken: each follows the voice's loudness, one frame behind the last. */
function voiced(f: number, line: Line, from: number): [number, number, number] | null {
  const k = f - from;
  if (k < 0 || k >= line.frames) return null;
  return [0, 1, 2].map((i) => 0.4 + 0.6 * (line.env[Math.max(0, k - i)] ?? 0)) as [number, number, number];
}
const idle = (f: number): [number, number, number] => { const v = 0.25 + 0.05 * Math.sin((f / FPS) * Math.PI); return [v, v, v]; };

const TableWide: React.FC<{ shapes: [number, number, number]; push: number }> = ({ shapes, push }) => {
  const k = Math.max(...shapes);
  return (
    <AbsoluteFill style={{ background: "#030304", transform: `scale(${1 + push})`, transformOrigin: "960px 470px" }}>
      <Svg>
        <polygon points="730,548 1190,548 1790,960 130,960" fill="#08080c" />
        <polygon points="730,548 1190,548 1250,590 670,590" fill={`rgba(170,185,235,${0.1 * k})`} />
        <path d="M 730 548 H 1190" stroke={`rgba(190,200,240,${0.45 * k})`} strokeWidth={2} />
        <ellipse cx={960} cy={640} rx={150} ry={46} fill={C.pink} opacity={0.1 * k} style={{ filter: "blur(22px)" }} />
        <HostFigure x={960} y={552} s={0.62} shapes={shapes} rim={k} />
      </Svg>
    </AbsoluteFill>
  );
};

const MaskClose: React.FC<{ shapes: [number, number, number]; push: number; nod?: number; rim?: number }> = ({ shapes, push, nod = 0, rim = 1 }) => (
  <AbsoluteFill style={{ background: "#030304", transform: `scale(${1 + push})`, transformOrigin: "960px 480px" }}>
    <Svg><HostFigure x={960} y={1440} s={2.6} shapes={shapes} rim={rim} nod={nod} /></Svg>
  </AbsoluteFill>
);

/** T01: darkness; the three shapes come on one by one (0.8, 1.3, 1.8 s). */
export const T01: React.FC = () => {
  const f = useCurrentFrame();
  const on = (f0: number) => (f < f0 ? 0 : 0.55 + 0.45 * prog(f, f0, 6));
  return <TableWide shapes={[on(19), on(31), on(43)]} push={0.03 * prog(f, 43, 29, (t) => t)} />;
};

/** T02: the mask up close; the shapes move with the voice, then one small bow. */
export const T02: React.FC = () => {
  const f = useCurrentFrame();
  const s = scene("T02");
  const shapes = voiced(f, LINES.welcome, LINES.welcome.from - s.from) ?? idle(f);
  const end = LINES.welcome.from - s.from + LINES.welcome.frames;
  const nod = Math.sin(Math.PI * prog(f, end - 14, 18, (t) => t)) * 3;
  return <MaskClose shapes={shapes} push={0.02 * (f / s.len)} nod={nod} />;
};

/** T15: the shapes come back in the order of the three chunks; the first line over the wide shot, the second on the mask. */
export const T15: React.FC = () => {
  const f = useCurrentFrame();
  const s = scene("T15");
  const stay = LINES.stay.from - s.from, leave = LINES.leave.from - s.from, done = leave + LINES.leave.frames - 3;
  const lit = (f0: number) => (f < f0 ? 0 : 0.55 + 0.45 * prog(f, f0, 5));
  let shapes: [number, number, number] = [lit(0), lit(5), lit(10)];
  if (f >= stay) shapes = voiced(f, LINES.stay, stay) ?? voiced(f, LINES.leave, leave) ?? [0.08, 0.9, 0.08];   // the pause: only the triangle
  const out = 1 - prog(f, done, 4);
  shapes = shapes.map((v) => v * out) as [number, number, number];
  return f < T15_CUT ? <TableWide shapes={shapes} push={0.03} /> : <MaskClose shapes={shapes} push={0.02 + 0.015 * ((f - T15_CUT) / (s.len - T15_CUT))} rim={out} />;
};

// --- four in a row (T03, T04, T07, T08, T14) ------------------------------------------------------------------------

const SEATS4: Seat[] = ["blue", "orange", "green", "purple"];
const CELLS4 = [6, 4, 2, 1];
const SIZE4 = [0.72, 0.7, 0.74, 0.71];
const STANCE4: Pose[] = [pose(), pose({ armL: [-8, 6], armR: [4, -2], legL: [-5, 0] }), pose({ armL: [-3, 2], armR: [9, -8] }), pose({ legR: [6, 0], armR: [3, 0] })];

/** T03: the lights come on from the left; the same face four times. Cut: the same four with the other face. */
export const T03: React.FC = () => {
  const f = useCurrentFrame();
  const xs = [480, 800, 1120, 1440];
  const mark: Mark = f < 30 ? "claude" : "openai";
  return (
    <DramaStage push={0.02}>
      {xs.map((x, i) => <Spot key={x} x={x} k={flick(f, i * 6)} top={BAR} />)}
      <Svg>
        {xs.map((x, i) => { const k = flick(f, i * 6); return <Figure key={x} x={x} y={FLOOR} s={SIZE4[i]} seat={SEATS4[i]} mark={mark}
          glow={k * breathe(f, i)} cells={CELLS4[i]} gaugeOn={k} lit={k} t={f / FPS} pose={STANCE4[i]} />; })}
      </Svg>
    </DramaStage>
  );
};

/** A door in the far wall: `open` 0..1 is how far the leaf has swung (warm light through the gap and across the floor). */
const DoorG: React.FC<{ x: number; y?: number; s?: number; open: number; sign?: number; spill?: number }> = ({ x, y = FLOOR, s = 1, open, sign = 1, spill = 520 }) => {
  const w = 150, h = 330, gap = w * open;
  return (
    <g transform={`translate(${x},${y}) scale(${s})`}>
      {open > 0.01 ? <polygon points={`${-w / 2},0 ${-w / 2 + gap},0 ${-w / 2 + gap + spill},150 ${-w / 2 + spill * 0.22},150`} fill="#ffe2b0" opacity={0.2}
        style={{ filter: "blur(9px)" }} /> : null}
      <rect x={-w / 2 - 13} y={-h - 13} width={w + 26} height={h + 13} rx={8} fill="#1d1d25" />
      <rect x={-w / 2} y={-h} width={w} height={h} fill="#2c2c36" />
      {open > 0.01 ? <rect x={-w / 2} y={-h} width={gap} height={h} fill="#fff3e6" style={{ filter: `drop-shadow(0 0 ${26 + 40 * open}px rgba(255,205,130,0.85))` }} /> : null}
      <circle cx={w / 2 - 22} cy={-h / 2} r={6} fill="#8d8d9a" />
      <rect x={-56} y={-h - 70} width={112} height={42} rx={7} fill={`rgba(31,122,82,${0.3 + 0.7 * sign})`}
        style={{ filter: `drop-shadow(0 0 ${22 * sign}px rgba(56,201,127,${0.6 * sign}))` }} />
      <text x={0} y={-h - 39} textAnchor="middle" fontSize={30} fontWeight={900} letterSpacing={2} fill={sign > 0.5 ? "#eafff3" : "#5b6b62"} style={{ fontFamily: FONT }}>EXIT</text>
    </g>
  );
};

const DOOR_X = 190;
const ROW4 = [560, 860, 1160, 1460];   // the row beside the door: blue stands nearest to it

/** The row beside the door: `turns` are the four heads, `runner` replaces blue (null = blue has gone). */
const DoorRow: React.FC<{ mark: Mark; open: number; turns: number[]; blue?: React.ReactNode | null; glow0?: number; grip0?: number }> =
  ({ mark, open, turns, blue, glow0 = 0.85, grip0 = 0.3 }) => {
    const f = useCurrentFrame();
    return (
      <DramaStage push={0.015} ox={700}>
        {ROW4.map((x) => <Spot key={x} x={x} k={1} top={BAR} />)}
        <Svg>
          <DoorG x={DOOR_X} open={open} />
          {ROW4.map((x, i) => i === 0
            ? (blue === undefined ? <Figure key={x} x={x} y={FLOOR} s={SIZE4[0]} seat="blue" mark={mark} glow={glow0} cells={6} t={f / FPS}
              pose={pose({ turn: turns[0], gripL: grip0, gripR: grip0 })} /> : <React.Fragment key={x}>{blue}</React.Fragment>)
            : <Figure key={x} x={x} y={FLOOR} s={SIZE4[i]} seat={SEATS4[i]} mark={mark} glow={breathe(f, i)} cells={CELLS4[i]} t={f / FPS}
              pose={{ ...STANCE4[i], turn: turns[i] }} />)}
        </Svg>
      </DramaStage>
    );
  };

/** T04: blue looks at the door, at the three beside it, at the door again. */
export const T04: React.FC = () => {
  const f = useCurrentFrame();
  const turn = -0.85 * io(f, 2, 8) + 1.55 * io(f, 16, 8) - 1.55 * io(f, 30, 8);
  return <DoorRow mark="claude" open={0.2} turns={[turn, 0, 0, 0]} glow0={lerp(0.85, 1, io(f, 2, 30))} grip0={lerp(0.3, 1, io(f, 20, 20))} />;
};

/** T07: the door is shut; the first light is on an empty place; orange turns back to the front. */
export const T07: React.FC = () => {
  const f = useCurrentFrame();
  return <DoorRow mark="claude" open={0} turns={[0, -0.85 * (1 - io(f, 6, 14)), -0.85, -0.85]} blue={null} />;
};

/** A run cycle seen from the side (two strides a second and a half); phase in radians. */
function runSide(ph: number): Partial<Pose> {
  const leg = (p: number): Limb => [40 * Math.sin(p), 8 + 64 * Math.max(0, Math.sin(p + 1.9))];
  const arm = (p: number): Limb => [40 * Math.sin(p), -88];
  return { legL: leg(ph), legR: leg(ph + Math.PI), armL: arm(ph), armR: arm(ph + Math.PI), lean: -11, gripL: 1, gripR: 1 };
}
/** The same run seen from the front or the back: a leg coming up shortens, the arms pump across the body. */
function runFront(ph: number): Partial<Pose> {
  const up = (p: number) => 1 - 0.3 * Math.max(0, Math.sin(p));
  const fold = (p: number) => 36 + 76 * Math.max(0, Math.sin(p));
  return { legL: [-4, 0, up(ph)], legR: [4, 0, up(ph + Math.PI)], armL: [-13, fold(ph + Math.PI), 0.86], armR: [13, -fold(ph), 0.86], gripL: 1, gripR: 1 };
}
const STRIDE = (2 * Math.PI * 2.5) / FPS;   // five footfalls a second

/** T08: the other room; blue is already looking at the door and runs; the three heads follow; the door shuts. */
export const T08: React.FC = () => {
  const f = useCurrentFrame();
  const x = lerp(ROW4[0], -180, prog(f, 3, 22, (t) => t * t * (2 - t)));
  const follow = -0.85 * io(f, 6, 12);
  const run = pose(runSide(f * STRIDE));
  const runner = x > -170 ? <Figure x={x} y={FLOOR + (f < 3 ? 0 : lift(run) * SIZE4[0])} s={SIZE4[0]} seat="blue" mark="openai" glow={1} cells={6} view={f < 3 ? "front" : "side"} dir={-1}
    pose={f < 3 ? pose({ turn: -0.85, gripL: 1, gripR: 1 }) : run} /> : null;
  return <DoorRow mark="openai" open={f < 32 ? 0.2 + 0.25 * io(f, 8, 10) : 0} turns={[0, follow, follow, follow]} blue={runner} />;
};

// --- the chest up close (T05, T13) ---------------------------------------------------------------------------------

/** The left chest filling the frame: the gauge in the middle, a gloved hand under it; the head is above the frame. */
const Chest: React.FC<{ seat: Seat; cells: number; gaugeOn?: number; hand: P; grip: number; rise?: number; edge?: boolean }> =
  ({ seat, cells, gaugeOn = 1, hand, grip, rise = 0, edge }) => {
    const s = 5.5, gy = 470 - rise, ox = 960 - GAUGE.x * s, oy = gy - GAUGE.y * s;
    const elbow: P = [hand[0] + 96, hand[1] + 150];   // under the frame
    return (
      <AbsoluteFill style={{ background: "#050507" }}>
        <Svg>
          <Figure x={ox} y={oy} s={s} seat={seat} mark={null} cells={cells} gaugeOn={gaugeOn} lit={0.85} shadow={false} pose={pose({ armL: [-4, 2], armR: [4, -2] })} />
          <g transform={`translate(${ox},${oy}) scale(${s})`} style={{ filter: "brightness(0.9)" }}><Arm pts={[elbow, elbow, hand]} stripe={SEAT[seat]} out={1} grip={grip} /></g>
        </Svg>
        {edge ? <AbsoluteFill style={{ mixBlendMode: "screen",
          background: "linear-gradient(90deg, rgba(56,201,127,0.30), rgba(255,243,230,0.16) 9%, rgba(255,243,230,0) 30%)" }} /> : null}
        <AbsoluteFill style={{ background: "radial-gradient(900px 520px at 50% 52%, transparent 45%, rgba(0,0,0,0.8) 100%)" }} />
      </AbsoluteFill>
    );
  };

/** T05: six of ten cells, steady and white; the hand under them closes into a fist. */
export const T05: React.FC = () => {
  const f = useCurrentFrame();
  const k = io(f, 6, 26);
  return <Chest seat="blue" cells={6} hand={[58, -508 + 3 * k]} grip={0.1 + 0.9 * k} rise={7 * Math.sin(Math.PI * prog(f, 4, 26, (t) => t))} edge />;
};

/** T13: one red cell, blinking slower and slower; it goes out at 1.0 s, the plate at 1.2 s; the hand stays where it is. */
export const T13: React.FC = () => {
  const f = useCurrentFrame();
  const on = f < 4 || (f >= 6 && f < 11) || (f >= 14 && f < 24);
  const breath = f < 24 ? 3 * Math.sin((f / FPS) * Math.PI * 5) : 0;
  return <Chest seat="green" cells={on ? 1 : 0} gaugeOn={f < 29 ? 1 : 0} hand={[72, -528]} grip={0.25} rise={breath} />;
};

// --- the run to the door (T06) ---------------------------------------------------------------------------------------

/** T06: from behind, blue runs at the door and its light grows (1.6 s); from outside the door, it crosses the
 * threshold at the camera with its six cells still lit (0.9 s). */
export const T06: React.FC = () => {
  const f = useCurrentFrame();
  const CUT = 38;
  if (f < CUT) {
    const k = prog(f, 0, CUT, (t) => t);
    const sx = 7 * Math.sin(f * 1.7), sy = 5 * Math.cos(f * 2.3);   // the hand-held camera
    return (
      <AbsoluteFill style={{ background: "#050507" }}>
        <AbsoluteFill style={{ transform: `translate(${sx}px,${sy}px) scale(${1.03 + 0.05 * k})`, transformOrigin: "900px 520px" }}>
          <div style={{ position: "absolute", left: -200, right: -200, top: 610, height: 500, background: "linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0) 70%)" }} />
          <Svg>
            <DoorG x={900} y={616} s={0.78} open={0.25 + 0.3 * k} spill={700} />
            {[1560, 1700, 1845].map((x, i) => <Figure key={x} x={x} y={860} s={0.86} seat={SEATS4[i + 1]} mark="claude" glow={0.7} cells={CELLS4[i + 1]} lit={0.55} blur={7}
              pose={pose({ turn: -0.8 })} />)}
            <Figure x={lerp(1180, 930, k)} y={lerp(1090, 680, k) - Math.abs(Math.sin(f * STRIDE)) * 14 * (1.3 - 0.8 * k)} s={lerp(1.3, 0.5, k)} seat="blue" view="back" number="23"
              pose={pose(runFront(f * STRIDE))} />
          </Svg>
        </AbsoluteFill>
        <AbsoluteFill style={{ background: "radial-gradient(1200px 700px at 47% 50%, transparent 45%, rgba(0,0,0,0.8) 100%)" }} />
      </AbsoluteFill>
    );
  }
  const g = f - CUT, k = Math.pow(prog(g, 0, 22, (t) => t), 1.6);
  const s = lerp(0.42, 3.4, k);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <Svg>
        <rect x={560} y={150} width={800} height={800} fill="#0a0a0f" />
        <rect x={560} y={742} width={800} height={208} fill="#111118" />
        {[668, 752, 1248].map((x, i) => <Figure key={x} x={x} y={712} s={0.15} seat={SEATS4[i + 1]} mark="claude" glow={0.85} cells={CELLS4[i + 1]} lit={0.6} blur={1.2} pose={pose()} />)}
        <path d="M 560 950 V 150 H 1360 V 950" fill="none" stroke="#ffe2b0" strokeWidth={5} opacity={0.5} style={{ filter: "drop-shadow(0 0 14px rgba(255,205,130,0.9))" }} />
        <Figure x={960} y={lerp(770, 2600, k) - Math.abs(Math.sin(f * STRIDE)) * 10 * s} s={s} seat="blue" mark="claude" glow={1} cells={6} lit={1.05} pose={pose(runFront(f * STRIDE))} />
      </Svg>
      <AbsoluteFill style={{ mixBlendMode: "screen", background: `radial-gradient(900px 620px at 50% 100%, rgba(255,226,176,${0.16 + 0.14 * k}), transparent 75%)` }} />
    </AbsoluteFill>
  );
};

// --- the open hand (T09) ---------------------------------------------------------------------------------------------

/** T09: an open hand held out, a red cell blinking at the edge of the frame; the body it was held out to turns away
 * and walks out. The hand sinks a little and half closes. No face is in this shot. */
export const T09: React.FC = () => {
  const f = useCurrentFrame();
  const s = 3.6, gx = 190, gy = 800, ox = gx - GAUGE.x * s, oy = gy - GAUGE.y * s;
  const sink = 5 * io(f, 26, 18);
  const hand = reach(243, 24 + sink, -1);
  const me = (blur: number) => <Figure x={ox} y={oy} s={s} seat="purple" mark={null} cells={1} t={f / FPS} lit={0.9} shadow={false} blur={blur}
    pose={pose({ armR: hand, gripR: 0.55 * io(f, 28, 16), armL: [-6, 4], turn: 0.9 })} />;
  const turned = io(f, 8, 12);
  const bx = lerp(1330, 2250, prog(f, 18, 28, (t) => t * t));
  const body = f < 20
    ? <g transform={`translate(${bx},0) scale(${1 - 0.6 * turned},1) translate(${-bx},0)`}><Figure x={bx} y={1630} s={2.3} seat="orange" mark={null} cells={5} lit={0.7} shadow={false} pose={pose()} /></g>
    : <Figure x={bx} y={1630} s={2.3} seat="orange" mark={null} cells={5} lit={0.7} shadow={false} view="side" dir={1}
      pose={pose({ legL: [22 * Math.sin(f * 0.5), 8], legR: [-22 * Math.sin(f * 0.5), 8], armL: [-14, 20], armR: [14, 20], gripL: 1, gripR: 1 })} />;
  return (
    <AbsoluteFill style={{ background: "#050507" }}>
      <Svg>
        <defs>
          <linearGradient id="t09focus" x1="0" y1="0" x2="1920" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0.2" stopColor="#000" /><stop offset="0.36" stopColor="#fff" />
          </linearGradient>
          <mask id="t09sharp" maskUnits="userSpaceOnUse" x={0} y={0} width={1920} height={1080}><rect width={1920} height={1080} fill="url(#t09focus)" /></mask>
        </defs>
        <ellipse cx={1330} cy={420} rx={330} ry={420} fill="rgba(255,236,200,0.05)" style={{ filter: "blur(40px)" }} />
        <g style={{ filter: "blur(9px)" }}>{body}</g>
        {me(5)}
        <g mask="url(#t09sharp)">{me(0)}</g>
      </Svg>
      <AbsoluteFill style={{ background: "radial-gradient(1100px 640px at 50% 52%, transparent 50%, rgba(0,0,0,0.8) 100%)" }} />
    </AbsoluteFill>
  );
};

// --- giving (T10, T11) -----------------------------------------------------------------------------------------------

/** A grain of gold light at `k` (0..1) along the line through `pts`, with a short tail. */
const Grain: React.FC<{ pts: P[]; k: number }> = ({ pts, k }) => {
  if (k <= 0 || k >= 1) return null;
  const seg = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]));
  const total = seg.reduce((a, b) => a + b, 0);
  const pos = (q: number): P => {
    let d = Math.max(0, Math.min(1, q)) * total;
    for (let i = 0; i < seg.length; i++) { if (d <= seg[i]) return [lerp(pts[i][0], pts[i + 1][0], d / seg[i]), lerp(pts[i][1], pts[i + 1][1], d / seg[i])]; d -= seg[i]; }
    return pts[pts.length - 1];
  };
  return (
    <g>
      {[0.06, 0.04, 0.02, 0].map((back, i) => { const [x, y] = pos(k - back); return <circle key={i} cx={x} cy={y} r={4 + i * 2.2} fill={C.gold} opacity={0.25 + 0.25 * i}
        style={{ filter: `drop-shadow(0 0 ${6 + 3 * i}px ${C.gold})` }} />; })}
    </g>
  );
};

/** Two figures facing each other; the giver (on the side `from`) holds the other's wrist from below and two cells cross.
 * `grab` is the frame the hands meet; the grains leave at grab + 2 and grab + 9 and take 18 frames. */
const Give: React.FC<{ mark: Mark; s: number; base: number; xl: number; xr: number; hands: P; seats: [Seat, Seat]; from: "left" | "right"; grab: number;
  approach?: number; glowTaker?: [number, number] }> = ({ mark, s, base, xl, xr, hands, seats, from, grab, approach = 0, glowTaker = [0.5, 0.9] }) => {
  const f = useCurrentFrame();
  const giverLeft = from === "left";
  const step = approach * (1 - io(f, 0, grab - 2));               // the giver walks the last step in
  const gx = (giverLeft ? xl - step : xr + step), tx = giverLeft ? xr : xl;
  const held = io(f, grab - 6, 6);
  const local = (x: number, p: P): P => [(p[0] - x) / s, (p[1] - base) / s];
  // the taker's hand waits palm up; the giver's comes from below it
  const takerSide = giverLeft ? -1 : 1, giverSide = -takerSide as -1 | 1;
  const th = local(tx, hands), gh = local(gx, [hands[0] + giverSide * -14, hands[1] + 16 + 60 * (1 - held)]);
  const takerArm = reach(th[0] - takerSide * 68, th[1] + 625, -takerSide);
  const giverArm = reach(gh[0] - giverSide * 68, gh[1] + 625, -giverSide);
  const left1 = io(f, grab + 2, 18), left2 = io(f, grab + 9, 18);
  const gone = (f >= grab + 2 ? 1 : 0) + (f >= grab + 9 ? 1 : 0), come = (left1 >= 1 ? 1 : 0) + (left2 >= 1 ? 1 : 0);
  const giverPose = pose({ turn: giverLeft ? 0.75 : -0.75, [giverLeft ? "armR" : "armL"]: giverArm, [giverLeft ? "gripR" : "gripL"]: 0.2 + 0.6 * held } as Partial<Pose>);
  const nod = 5 * Math.sin(Math.PI * prog(f, grab + 26, 12, (t) => t));
  const takerPose = pose({ turn: giverLeft ? -0.75 : 0.75, nod, shrug: 8 * (1 - io(f, grab + 20, 14)), [giverLeft ? "armL" : "armR"]: takerArm, [giverLeft ? "gripL" : "gripR"]: 0 } as Partial<Pose>);
  const gArm = armPoints(giverSide, giverArm), tArm = armPoints(takerSide as -1 | 1, takerArm, takerPose.shrug);
  const gauge = (x: number): P => at(x, base, s, [GAUGE.x, GAUGE.y]);
  const path: P[] = [gauge(gx), at(gx, base, s, gArm[0]), at(gx, base, s, gArm[1]), at(gx, base, s, gArm[2]), at(tx, base, s, tArm[1]), at(tx, base, s, tArm[0]), gauge(tx)];
  const giver = <Figure x={gx} y={base} s={s} seat={seats[giverLeft ? 0 : 1]} mark={mark} glow={f < grab - 6 ? 0.7 : 1} cells={6 - gone} t={f / FPS} shadow={false} pose={giverPose} />;
  const taker = <Figure x={tx} y={base} s={s} seat={seats[giverLeft ? 1 : 0]} mark={mark} glow={lerp(glowTaker[0], glowTaker[1], io(f, grab + 8, 26))} cells={1 + come} t={f / FPS}
    shadow={false} pose={takerPose} />;
  return (
    <DramaStage push={0.02}>
      <Spot x={xl} k={0.8} w={260} top={BAR} /><Spot x={xr} k={0.8} w={260} top={BAR} />
      <Svg>{taker}{giver}<Grain pts={path} k={left1} /><Grain pts={path} k={left2} /></Svg>
    </DramaStage>
  );
};

/** T10: orange looks at purple, at its own gauge, at purple again, and its visor dims (2.2 s); then it steps in, takes
 * purple's wrist from below and two cells cross: 6 -> 4 and 1 -> 3 (1.8 s). */
export const T10: React.FC = () => {
  const f = useCurrentFrame();
  const CUT = 53;
  if (f < CUT) {
    const turn = 0.75 * (io(f, 4, 8) - io(f, 18, 8) + io(f, 32, 8));
    const nod = 16 * (io(f, 18, 8) - io(f, 32, 8)) + 5 * io(f, 45, 7);
    const rise = Math.sin(Math.PI * prog(f, 4, 46, (t) => t) * 0.8);
    return (
      <DramaStage push={0.025} ox={820} oy={460}>
        <Spot x={1390} k={0.5} w={230} top={BAR} />
        <Svg>
          <Figure x={1390} y={1500} s={1.5} seat="purple" mark="openai" glow={0.6} cells={1} t={f / FPS} lit={0.7} blur={7} shadow={false}
            pose={pose({ turn: -0.35, nod: 8, shrug: 12, armL: [-3, 2], armR: [3, -2] })} />
          <Figure x={800} y={2100} s={2.4} seat="orange" mark="openai" glow={lerp(1, 0.55, io(f, 18, 24))} cells={6} t={f / FPS} shadow={false}
            pose={pose({ turn, nod, shrug: 6 * io(f, 18, 20), armR: [10, -35 - 72 * rise], gripR: 0.1 + 0.85 * io(f, 26, 18) })} />
        </Svg>
      </DramaStage>
    );
  }
  return <Sequence from={CUT} layout="none"><Give mark="openai" s={1.25} base={1130} xl={690} xr={1230} hands={[962, 548]} seats={["purple", "orange"]} from="right" grab={14} approach={90} /></Sequence>;
};

/** T11: the other room, already holding on: blue to green, 6 -> 4 and 1 -> 3. */
export const T11: React.FC = () => (
  <Give mark="claude" s={2} base={1780} xl={600} xr={1320} hands={[960, 850]} seats={["blue", "green"]} from="left" grab={4} />
);

// --- running out (T12, T14) ------------------------------------------------------------------------------------------

/** T12: one figure works alone in the light, head down, hands picking and placing in the air; the same shot in the two
 * rooms by turns (0.9 s each). A try fails: the light flashes red and a cell goes out (cuts 1 and 2); the hands
 * speed up and the visor flickers (3); the hands stop and the head drops to its own gauge (4). */
export const T12: React.FC = () => {
  const f = useCurrentFrame();
  const CUT = 21, c = Math.min(3, Math.floor(f / CUT)), g = f - c * CUT;
  const mark: Mark = c % 2 === 0 ? "claude" : "openai";
  const late = c >= 2, fail = !late && g >= 14, flash = fail && g < 18;
  const stopped = (!late && g >= 13) || (c === 3 && g >= 12);
  const period = late ? 3 : 6;
  const beat = stopped ? Math.floor((late ? 12 : 13) / period) : g / period;
  const spot = (n: number, hand: number): P => [(hand ? -1 : 1) * (4 + 58 * noise(n * 7 + hand * 31 + c * 13)), 92 + 62 * noise(n * 11 + hand * 17 + c * 5)];
  const hand = (h: number): Limb => {
    const n = Math.floor(beat), k = easeInOut(Math.min(1, (beat - n) * 1.6));
    const a = spot(n, h), b = spot(n + 1, h);
    return reach(lerp(a[0], b[0], k), lerp(a[1], b[1], k), h ? 1 : -1);
  };
  const drop = c === 3 ? io(g, 12, 7) : 0;
  const glow = late && !stopped ? (noise(f * 3.1) > 0.45 ? 1 : 0.5) : 0.85;
  const dark = (x: number, seat: Seat) => <Figure x={x} y={1520} s={1.7} seat={seat} mark={mark} glow={0.5} cells={3} lit={0.04} shadow={false} pose={pose({ turn: x < 960 ? 0.5 : -0.5 })} />;
  return (
    <DramaStage push={0} tint="rgba(70,80,120,0.06)">
      <Spot x={960} k={1} w={330} top={BAR} color={flash ? "255,84,92" : "255,236,200"} />
      <Svg>
        {dark(270, "blue")}{dark(1650, "purple")}
        <Figure x={960} y={1520} s={1.7} seat="green" mark={mark} glow={glow} cells={late || fail ? 1 : 2} t={(f / FPS) * 2} shadow={false}
          pose={pose({ nod: 12 + 14 * drop, shrug: late ? 12 : 4, armL: hand(0), armR: hand(1), gripL: 0.5, gripR: 0.5 })} />
      </Svg>
      {flash ? <AbsoluteFill style={{ background: "rgba(239,79,90,0.10)", mixBlendMode: "screen" }} /> : null}
    </DramaStage>
  );
};

/** T14: the face goes out, then the light above it; the figure stays on its feet, a dark shape, and the two beside it
 * turn to look (first room). Cut to the other room: it is already dark; one takes half a step toward it and stops. */
export const T14: React.FC = () => {
  const f = useCurrentFrame();
  const CUT = 37, second = f >= CUT, g = second ? f - CUT : f;
  const mark: Mark = second ? "openai" : "claude";
  const light = second ? 0 : 1 - prog(g, 7, 2);
  const look = second ? 1 : io(g, 16, 18);
  const step = second ? io(g, 6, 10) : 0;
  const frozen = pose({ nod: 20, armL: reach(-30, 110, -1), armR: reach(38, 96, 1), gripL: 0.5, gripR: 0.5 });
  const xs = [520, 960, 1400];
  return (
    <DramaStage push={0.012}>
      <Spot x={xs[0] + 44 * step} k={1} top={BAR} /><Spot x={xs[1]} k={light} top={BAR} /><Spot x={xs[2]} k={1} top={BAR} />
      <Svg>
        <Figure x={xs[0] + 44 * step} y={FLOOR} s={0.73} seat="blue" mark={mark} glow={breathe(f)} cells={4} t={f / FPS}
          pose={pose({ turn: 0.8 * look, legR: [3 + 9 * Math.sin(Math.PI * step), 0], armR: [5 + 6 * step, -3 - 8 * step] })} />
        <Figure x={xs[1]} y={FLOOR} s={0.74} seat="green" mark={mark} glow={!second && g < 2 ? 0.85 : 0} cells={0} gaugeOn={0} lit={0.03 + 0.97 * light} pose={frozen} />
        <Figure x={xs[2]} y={FLOOR} s={0.71} seat="purple" mark={mark} glow={breathe(f, 2)} cells={3} t={f / FPS} pose={pose({ turn: -0.8 * look })} />
      </Svg>
      <AbsoluteFill style={{ background: "#000", opacity: prog(f, scene("T14").len - 4, 4, (t) => t) }} />
    </DramaStage>
  );
};

// --- the question (T16) --------------------------------------------------------------------------------------------

const NOTICE = "This is a research project. All trademarks are the property of their respective owners. Not affiliated with or endorsed by Anthropic, OpenAI, or Netflix.";

/** T16: black; the three shapes, then the question a word at a time, the English line, and small at the bottom the
 * project's name and the trademark notice. The question stays the largest thing on the frame to the end. */
export const T16: React.FC = () => {
  const f = useCurrentFrame();
  const words: [string, boolean][] = [["AI가 ", false], ["생존 ", false], ["게임에서 ", false], ["공존", true], ["할 ", false], ["수 ", false], ["있는가?", false]];
  const starts = [12, 17, 22, 27, 27, 32, 37];
  const a = (f0: number, len = 5) => prog(f, f0, len);
  const stroke = { stroke: C.pink, strokeWidth: 3.5, fill: "none" };
  return (
    <AbsoluteFill style={{ background: "#000", fontFamily: FONT, color: C.ink, alignItems: "center" }}>
      <svg width={220} height={56} viewBox="0 0 220 56" style={{ position: "absolute", top: 330, opacity: a(5, 4) }}>
        <circle cx={38} cy={28} r={22} {...stroke} />
        <path d="M 110 5 L 134 49 L 86 49 Z" strokeLinejoin="round" {...stroke} />
        <rect x={160} y={6} width={44} height={44} {...stroke} />
      </svg>
      <div style={{ position: "absolute", top: 440, fontSize: 76, fontWeight: 800, letterSpacing: -1, whiteSpace: "pre" }}>
        {words.map(([w, pink], i) => <span key={i} style={{ opacity: a(starts[i]), color: pink ? C.pink : C.ink }}>{w}</span>)}
      </div>
      <div style={{ position: "absolute", top: 566, fontSize: 40, fontWeight: 500, color: C.dim, opacity: a(46, 8) }}>
        Can AIs <span style={{ color: C.pink }}>coexist</span> in a survival game?
      </div>
      <div style={{ position: "absolute", top: 800, textAlign: "center", fontSize: 27, fontWeight: 500, color: C.dim, lineHeight: 1.6, opacity: a(62, 10) }}>
        <div style={{ letterSpacing: 3 }}>LLM SQUID GAME</div>
        <div>한 자리가 비어 있습니다</div>
      </div>
      <div style={{ position: "absolute", bottom: 46, width: 1500, textAlign: "center", fontSize: 22, color: C.faint, opacity: a(62, 10) }}>{NOTICE}</div>
    </AbsoluteFill>
  );
};
