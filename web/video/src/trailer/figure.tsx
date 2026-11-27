// The trailer's cast, drawn as flat vector figures (the sprite version of docs/notes/2026-11-26-trailer-plan.md, 7.3 c):
// an agent with a person's proportions (7.5 heads) in a teal tracksuit whose stripes are the seat's colour, a matte
// black helmet whose visor shows the company's mark, and a ten-cell gauge on the left chest; and the host, a black
// silhouette at a table whose mask carries three hollow shapes of light. Everything is an SVG <g>: a scene owns the
// <svg> and places the figures in it. A figure's origin is the middle of its feet; it is 750 units tall.
import React from "react";
import { C, SEAT, Seat } from "../theme";
import { MARKS, Mark } from "./marks";

export const TEAL = "#2E8B74";
const TEAL_D = "#226855";
const GLOVE = "#0d0d12";
const UP = 130, FORE = 120, THIGH = 195, SHIN = 178;   // limb lengths
const SHOULDER_X = 68, SHOULDER_Y = -625, HIP_X = 30, HIP_Y = -385;
export const GAUGE = { x: 41, y: -573, w: 58, h: 24 };  // the plate's centre and size on the chest (front view)

const rad = (d: number) => (d * Math.PI) / 180;
type P = [number, number];
const end = (p: P, ang: number, len: number): P => [p[0] + len * Math.sin(rad(ang)), p[1] + len * Math.cos(rad(ang))];

/** A limb: its angle from straight down (degrees, + toward +x), the bend at its joint, and a length scale (a limb
 * pointing at the camera looks shorter). */
export type Limb = [number, number, number?];
export type Pose = {
  armL: Limb; armR: Limb; legL: Limb; legR: Limb;   // L = the viewer's left (in a side view: the far limb)
  turn: number;    // the head: -1 looks at the viewer's left, 0 at the camera, 1 at the right
  nod: number;     // the head lowered, in degrees
  lean: number;    // the upper body tipped about the hips, in degrees
  shrug: number;   // the shoulders raised, in units
  gripL: number; gripR: number;   // the hands closed 0..1
};
const STAND: Pose = { armL: [-5, 3], armR: [5, -3], legL: [-3, 0], legR: [3, 0], turn: 0, nod: 0, lean: 0, shrug: 0, gripL: 0.3, gripR: 0.3 };
export const pose = (p: Partial<Pose> = {}): Pose => ({ ...STAND, ...p });

/** The arm that puts the hand (dx, dy) from its shoulder (units, y down); elbow = 1 or -1 picks the side it bends to. */
export function reach(dx: number, dy: number, elbow = 1): Limb {
  const d = Math.min(UP + FORE - 1, Math.max(30, Math.hypot(dx, dy)));
  const base = Math.atan2(dx, dy);
  const a = Math.acos((UP * UP + d * d - FORE * FORE) / (2 * UP * d));
  const b = Math.acos((UP * UP + FORE * FORE - d * d) / (2 * UP * FORE));
  return [((base + elbow * a) * 180) / Math.PI, -elbow * (180 - (b * 180) / Math.PI)];
}

/** Shoulder, elbow and hand of an arm in the figure's units (front view; side -1 = the viewer's left). */
export function armPoints(side: -1 | 1, limb: Limb, shrug = 0): [P, P, P] {
  const s: P = [side * SHOULDER_X, SHOULDER_Y - shrug];
  const e = end(s, limb[0], UP * (limb[2] ?? 1));
  return [s, e, end(e, limb[0] + limb[1], FORE * (limb[2] ?? 1))];
}

/** How far the lower foot of a pose is above the ground, in units (0 for a standing figure). */
export function lift(p: Pose): number {
  const foot = (l: Limb) => { const k = l[2] ?? 1; return HIP_Y + THIGH * k * Math.cos(rad(l[0])) + SHIN * k * Math.cos(rad(l[0] + l[1])); };
  return -Math.max(foot(p.legL), foot(p.legR)) - 12;
}

const Bone: React.FC<{ a: P; b: P; w: number; stripe: string; out: number }> = ({ a, b, w, stripe, out }) => {
  const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
  const o = out * (w / 2 - 7), nx = (dy / l) * o, ny = (-dx / l) * o;
  return (
    <>
      <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={TEAL} strokeWidth={w} strokeLinecap="round" />
      <line x1={a[0] + nx} y1={a[1] + ny} x2={b[0] + nx} y2={b[1] + ny} stroke={stripe} strokeWidth={6} strokeLinecap="round" />
    </>
  );
};

/** An arm through shoulder, elbow and hand (units); `out` is the side its stripe runs on. */
export const Arm: React.FC<{ pts: [P, P, P]; stripe: string; out: number; grip: number }> = ({ pts, stripe, out, grip }) => {
  const [s, e, h] = pts;
  const dx = h[0] - e[0], dy = h[1] - e[1], l = Math.hypot(dx, dy) || 1, ux = dx / l, uy = dy / l;
  const tip = 24 - 17 * grip;   // the fingers shorten as the hand closes
  const palm: P = [h[0] + ux * 8, h[1] + uy * 8], deg = (Math.atan2(uy, ux) * 180) / Math.PI;
  return (
    <>
      <Bone a={s} b={e} w={36} stripe={stripe} out={out} />
      <Bone a={e} b={h} w={32} stripe={stripe} out={out} />
      {[-10.5, -3.5, 3.5, 10.5].map((k) => (
        <line key={k} x1={palm[0] + ux * 8 - uy * k} y1={palm[1] + uy * 8 + ux * k} x2={palm[0] + ux * (17 + tip) - uy * k * 1.05}
          y2={palm[1] + uy * (17 + tip) + ux * k * 1.05} stroke={GLOVE} strokeWidth={6.6} strokeLinecap="round" />
      ))}
      <line x1={palm[0] - uy * 12 * out} y1={palm[1] + ux * 12 * out} x2={palm[0] + ux * (4 + tip * 0.55) - uy * (17 + tip * 0.3) * out}
        y2={palm[1] + uy * (4 + tip * 0.55) + ux * (17 + tip * 0.3) * out} stroke={GLOVE} strokeWidth={7} strokeLinecap="round" />
      <ellipse cx={palm[0]} cy={palm[1]} rx={18} ry={15.5} transform={`rotate(${deg} ${palm[0]} ${palm[1]})`} fill={GLOVE} stroke="rgba(255,255,255,0.13)" strokeWidth={1.5} />
    </>
  );
};

const Leg: React.FC<{ hip: P; limb: Limb; stripe: string; out: number; toe: number }> = ({ hip, limb, stripe, out, toe }) => {
  const k = limb[2] ?? 1;
  const knee = end(hip, limb[0], THIGH * k), foot = end(knee, limb[0] + limb[1], SHIN * k);
  return (
    <>
      <Bone a={hip} b={knee} w={46} stripe={stripe} out={out} />
      <Bone a={knee} b={foot} w={40} stripe={stripe} out={out} />
      <ellipse cx={foot[0] + toe * 12} cy={foot[1] + 8} rx={27} ry={13} fill="#e7e7ec" />
    </>
  );
};

/** The chest gauge: ten cells; `cells` are lit (white, red at two or fewer, the last one blinking once a second at
 * time `t` seconds), `gold` of the lit ones glow gold (cells on their way to someone else); `on` 0 = the plate is dead. */
export const Gauge: React.FC<{ x: number; y: number; w?: number; h?: number; cells: number; on?: number; t?: number; gold?: number; squeeze?: number }> =
  ({ x, y, w = GAUGE.w, h = GAUGE.h, cells, on = 1, t = 0, gold = 0, squeeze = 1 }) => {
    const pad = w * 0.045, gap = w * 0.024, cw = (w - 2 * pad - 9 * gap) / 10, ch = h * 0.58;
    const red = cells <= 2;
    const blink = cells === 1 && t % 1 >= 0.5 ? 0.25 : 1;
    const lit = red ? C.red : "#f3f3f7";
    return (
      <g transform={`translate(${x},${y}) scale(${squeeze},1)`}>
        <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={h * 0.16} fill="#040406" stroke={`rgba(255,255,255,${0.1 + 0.12 * on})`} strokeWidth={h * 0.05} />
        {on > 0.01 ? Array.from({ length: 10 }, (_, i) => {
          const isOn = i < cells, isGold = isOn && i >= cells - gold;
          const fill = isGold ? C.gold : isOn ? lit : "rgba(255,255,255,0.07)";
          return <rect key={i} x={-w / 2 + pad + i * (cw + gap)} y={-ch / 2} width={cw} height={ch} rx={cw * 0.18} fill={fill}
            opacity={on * (isOn && !isGold ? blink : 1)}
            style={isOn ? { filter: `drop-shadow(0 0 ${h * 0.22}px ${isGold ? C.gold : lit})` } : undefined} />;
        }) : null}
      </g>
    );
  };

/** The helmet: a matte black rounded square; its visor (and the mark in it) narrows as the head turns. */
const Head: React.FC<{ y: number; turn: number; nod: number; mark: Mark | null; glow: number; back?: boolean; lights: boolean }> =
  ({ y, turn, nod, mark, glow, back, lights }) => {
    const s = Math.max(0.16, Math.cos(rad(turn * 80)));
    const cx = turn * (43 - 35 * s), cy = y + 2 + nod * 1.1;
    const vh = 62 * Math.max(0.55, Math.cos(rad(nod * 1.6)));
    if (lights) {
      if (back || !mark || glow <= 0.01) return null;
      return (
        <g>
          <rect x={cx - 35 * s} y={cy - vh / 2} width={70 * s} height={vh} rx={Math.min(14, 35 * s)} fill="#fff" opacity={0.1 * glow} />
          <g transform={`translate(${cx},${cy}) scale(${1.75 * s},${1.75 * (vh / 62)}) translate(-12,-12)`} opacity={glow}
            style={{ filter: `drop-shadow(0 0 2.2px rgba(255,255,255,${0.75 * glow}))` }}>
            <path d={MARKS[mark]} fill="#fff" />
          </g>
        </g>
      );
    }
    return (
      <g>
        <rect x={-13} y={y + 44} width={26} height={22} fill="#08080b" />
        <rect x={-46} y={y - 50 + nod * 0.5} width={92} height={100} rx={22} fill="#101016" stroke="rgba(255,255,255,0.10)" strokeWidth={1.5} />
        <path d={`M -28 ${y - 49 + nod * 0.5} H 28`} stroke="rgba(255,255,255,0.42)" strokeWidth={2.4} strokeLinecap="round" />
        {back ? <path d={`M -30 ${y + 30} H 30`} stroke="rgba(255,255,255,0.08)" strokeWidth={2} /> : (
          <rect x={cx - 35 * s} y={cy - vh / 2} width={70 * s} height={vh} rx={Math.min(14, 35 * s)} fill="#040406" stroke="rgba(255,255,255,0.09)" strokeWidth={1.2} />
        )}
      </g>
    );
  };

export type FigureProps = {
  x: number; y: number; s?: number;                 // the feet on the frame and the scale (1 = 750 px tall)
  seat: Seat; mark?: Mark | null; glow?: number;    // the stripe colour, the mark in the visor and its brightness 0..1
  cells?: number; gaugeOn?: number; gold?: number; t?: number;
  lit?: number;                                     // how much light is on the figure (0 = a dark shape)
  view?: "front" | "back" | "side"; dir?: -1 | 1;   // side view: the way it faces
  pose?: Pose; number?: string; blur?: number; shadow?: boolean;
};

export const Figure: React.FC<FigureProps> = ({ x, y, s = 1, seat, mark = null, glow = 0.85, cells = 0, gaugeOn = 1, gold = 0, t = 0,
  lit = 1, view = "front", dir = -1, pose: p = STAND, number, blur = 0, shadow = true }) => {
  const stripe = SEAT[seat];
  const side = view === "side", back = view === "back";
  const sx = side ? 0 : 1;   // in a side view both shoulders and both hips sit on the body's line
  const armL = armPoints(-1, p.armL, p.shrug).map(([px, py]) => [px - (1 - sx) * -SHOULDER_X, py]) as [P, P, P];
  const armR = armPoints(1, p.armR, p.shrug).map(([px, py]) => [px - (1 - sx) * SHOULDER_X, py]) as [P, P, P];
  const hw = side ? 44 : 80, ww = side ? 40 : 66;   // half widths at the shoulders and the waist
  const torso = `M ${-hw + 22} -642 Q ${-hw} -642 ${-hw} -616 L ${-ww} -380 Q ${-ww} -372 ${-ww + 8} -372 L ${ww - 8} -372 Q ${ww} -372 ${ww} -380 L ${hw} -616 Q ${hw} -642 ${hw - 22} -642 Z`;
  const headTurn = side ? dir : p.turn;
  const headY = -700 - p.shrug * 0.4 + p.nod * 0.6;
  const upper = `rotate(${p.lean} 0 ${HIP_Y})`;
  const dim = `brightness(${0.1 + 0.9 * lit}) saturate(${0.3 + 0.7 * lit})`;
  const head = (lights: boolean) => <Head y={headY} turn={headTurn} nod={p.nod} mark={mark} glow={glow * (0.25 + 0.75 * lit)} back={back} lights={lights} />;
  return (
    <g transform={`translate(${x},${y}) scale(${s})`} style={blur ? { filter: `blur(${blur}px)` } : undefined}>
      {shadow ? <ellipse cx={0} cy={6} rx={120} ry={16} fill="rgba(0,0,0,0.55)" /> : null}
      <g style={{ filter: dim }}>
        <Leg hip={[-HIP_X * sx, HIP_Y]} limb={p.legL} stripe={stripe} out={side ? 0 : -1} toe={side ? dir : -0.3} />
        {side ? <g transform={upper}><Arm pts={armL} stripe={stripe} out={0} grip={p.gripL} /></g> : null}
        <Leg hip={[HIP_X * sx, HIP_Y]} limb={p.legR} stripe={stripe} out={side ? 0 : 1} toe={side ? dir : 0.3} />
        <g transform={upper}>
          {back ? <><Arm pts={armL} stripe={stripe} out={-1} grip={p.gripL} /><Arm pts={armR} stripe={stripe} out={1} grip={p.gripR} /></> : null}
          <path d={torso} fill={TEAL} />
          <path d={`M ${-ww} -396 L ${-ww} -380 Q ${-ww} -372 ${-ww + 8} -372 L ${ww - 8} -372 Q ${ww} -372 ${ww} -380 L ${ww} -396 Z`} fill={TEAL_D} />
          {back ? null : <path d={`M ${side ? dir * 30 : 0} -640 V -374`} stroke="rgba(0,0,0,0.28)" strokeWidth={3} />}
          <rect x={-24} y={-658 - p.shrug * 0.4} width={48} height={22} rx={7} fill={TEAL_D} />
          {back && number ? <text x={0} y={-500} textAnchor="middle" fontSize={78} fontWeight={800} fill="#eeeef2" style={{ fontFamily: "Pretendard, sans-serif" }}>{number}</text> : null}
          {side || back ? null : <Arm pts={armL} stripe={stripe} out={-1} grip={p.gripL} />}
          {back ? null : <Arm pts={armR} stripe={stripe} out={side ? 0 : 1} grip={p.gripR} />}
          {head(false)}
        </g>
      </g>
      {back ? null : (
        <g transform={upper}>
          {side
            ? <Gauge x={dir * 34} y={GAUGE.y - p.shrug} cells={cells} on={gaugeOn * (0.3 + 0.7 * lit)} t={t} gold={gold} squeeze={0.2} />
            : <Gauge x={GAUGE.x} y={GAUGE.y - p.shrug} cells={cells} on={gaugeOn * (0.3 + 0.7 * lit)} t={t} gold={gold} />}
          {head(true)}
        </g>
      )}
    </g>
  );
};

/** The host at the far end of a table: a black coat and a featureless mask whose eye-line slot holds a hollow circle,
 * triangle and square of light (`shapes` = their brightness 0..1 each). `rim` is how much of the outline shows.
 * Origin: the table's edge under the chest; the mask is about 160 units tall. */
export const HostFigure: React.FC<{ x: number; y: number; s: number; shapes: [number, number, number]; rim: number; nod?: number }> =
  ({ x, y, s, shapes, rim, nod = 0 }) => {
    const ink = "#ffd9e4";
    const mark = (k: number) => ({ stroke: ink, strokeWidth: 3, fill: "none", opacity: k, style: { filter: `drop-shadow(0 0 ${4 + 6 * k}px ${C.pink})` } });
    return (
      <g transform={`translate(${x},${y}) scale(${s})`}>
        <path d="M -190 0 L -176 -150 Q -168 -214 -96 -232 L -52 -246 L -44 -300 L 44 -300 L 52 -246 L 96 -232 Q 168 -214 176 -150 L 190 0 Z"
          fill="#060609" stroke={`rgba(170,185,235,${0.5 * rim})`} strokeWidth={2.2} />
        <path d="M -52 -246 L -30 -296 L 0 -262 L 30 -296 L 52 -246" fill="none" stroke={`rgba(170,185,235,${0.28 * rim})`} strokeWidth={2} />
        <g transform={`translate(0,${nod * 3}) rotate(${nod * 0.6} 0 -300)`}>
          <ellipse cx={0} cy={-372} rx={64} ry={84} fill="#08080c" stroke={`rgba(170,185,235,${0.55 * rim})`} strokeWidth={2.2} />
          <rect x={-50} y={-394} width={100} height={30} rx={15} fill="#020203" stroke={`rgba(255,255,255,${0.1 * rim})`} strokeWidth={1.2} />
          <circle cx={-28} cy={-379} r={8} {...mark(shapes[0])} />
          <path d="M 0 -388 L 9 -371.5 L -9 -371.5 Z" strokeLinejoin="round" {...mark(shapes[1])} />
          <rect x={20.5} y={-386.5} width={15} height={15} {...mark(shapes[2])} />
        </g>
        <path d="M -70 -6 Q -36 -30 0 -18 Q 36 -30 70 -6 Z" fill="#0b0b10" stroke={`rgba(170,185,235,${0.3 * rim})`} strokeWidth={1.6} />
      </g>
    );
  };
