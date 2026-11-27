// The film version of the trailer (composition TrailerFilm): the scenes of timing.ts on the same clock as the sprite
// version, drawn on generated live-action plates (public/trailer/, made by web/tools/make_trailer_plates.py). The cast was
// generated with blank magenta panels where its visors and chest gauges are, and so was the wall monitor of the task
// shot; the script painted them out and wrote their corners to src/generated/plates.json, so the marks, the gauge
// cells and the task on the monitor are drawn here, in place and in perspective, at any brightness — and one plate
// serves both rooms: only the mark differs. The host is the site's guard in a pink suit; its mask is plain black, and
// HOST_SLOT says where its three shapes go. A still plate moves by a slow push-in; a clip plays as it was generated.
import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, Sequence, staticFile, useCurrentFrame } from "remotion";
import { C, FONT, easeInOut, lerp, prog } from "../theme";
import { Gauge } from "./figure";
import { MARKS, Mark } from "./marks";
import { BAR, CHANT_BEATS, FPS, LINES, Line, T15_CUT, scene } from "./timing";
import index from "../generated/plates.json";

type Pt = [number, number];
type Quad = [Pt, Pt, Pt, Pt];
type Track = Quad | (Quad | null)[] | null;
type Entry = { w: number; h: number; frames?: number; slot?: Track; screen?: Track; figures: { visor: Track; plate: Track }[] };
const PLATES = index as unknown as Record<string, Entry>;
const PW = 1920, PH = 823, TOP = (1080 - PH) / 2;
const io = (f: number, start: number, len: number) => prog(f, start, len, easeInOut);
/** The eye line of the host's mask on its two plates (measured on the plates: nothing in them marks it). */
const HOST_SLOT: Record<string, Quad> = {
  k01_table: [[918, 326], [1000, 326], [1000, 334], [918, 334]],
  k02_host: [[845, 228], [1065, 228], [1065, 242], [845, 242]],
};
const breathe = (f: number, phase = 0) => 0.9 + 0.06 * Math.sin((f / FPS) * (Math.PI / 2) + phase);

/** A panel's corners at clip frame i: a still has one quad; in a clip the quad is averaged with its neighbours (the
 * corners are found frame by frame and shake by a pixel) and the last known one is held where the panel was not found. */
function quadAt(t: Track, i: number): Quad | null {
  if (!t) return null;
  if (typeof (t as Quad)[0][0] === "number") return t as Quad;
  const list = t as (Quad | null)[];
  const k = Math.max(0, Math.min(list.length - 1, Math.round(i)));
  const near = [k - 1, k, k + 1].map((j) => list[j]).filter(Boolean) as Quad[];
  if (near.length) return [0, 1, 2, 3].map((c) => [0, 1].map((a) => near.reduce((s, q) => s + q[c][a], 0) / near.length)) as Quad;
  for (let j = k; j >= 0; j--) if (list[j]) return list[j];
  return null;
}

/** The CSS transform that lays a w x h box onto a quad (a projective map of the box's corners onto the quad's). */
function onto(w: number, h: number, q: Quad): string {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = q;
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3, dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3;
  const det = dx1 * dy2 - dx2 * dy1 || 1e-9;
  const g = (dx3 * dy2 - dx2 * dy3) / det, k = (dx1 * dy3 - dx3 * dy1) / det;
  const a = x1 - x0 + g * x1, b = x3 - x0 + k * x3, d = y1 - y0 + g * y1, e = y3 - y0 + k * y3;
  return `matrix3d(${a / w},${d / w},0,${g / w}, ${b / h},${e / h},0,${k / h}, 0,0,1,0, ${x0},${y0},0,1)`;
}
const Panel: React.FC<{ quad: Quad | null; w: number; h: number; children: React.ReactNode }> = ({ quad, w, h, children }) => quad ? (
  <div style={{ position: "absolute", left: 0, top: 0, width: w, height: h, transformOrigin: "0 0", transform: onto(w, h, quad) }}>{children}</div>
) : null;

/** What one figure of a plate shows: the mark on its visor and its brightness, the lit cells of its gauge. */
export type Fig = { mark?: Mark | null; glow?: number; cells?: number; gauge?: number; gold?: number; t?: number };

const Visor: React.FC<{ quad: Quad | null; mark: Mark; glow: number }> = ({ quad, mark, glow }) => glow <= 0.01 ? null : (
  <Panel quad={quad} w={100} h={100}>
    <div style={{ position: "absolute", inset: 0, borderRadius: 24, background: `radial-gradient(closest-side, rgba(255,255,255,${0.16 * glow}), rgba(255,255,255,${0.03 * glow}))` }} />
    <svg viewBox="0 0 24 24" style={{ position: "absolute", left: 19, top: 19, width: 62, height: 62, opacity: glow,
      filter: `drop-shadow(0 0 3px rgba(255,255,255,${0.9 * glow})) drop-shadow(0 0 12px rgba(200,220,255,${0.55 * glow}))` }}>
      <path d={MARKS[mark]} fill="#fff" />
    </svg>
  </Panel>
);

const Plate10: React.FC<{ quad: Quad | null; cells: number; on: number; gold?: number; t?: number }> = ({ quad, cells, on, gold = 0, t = 0 }) => (
  <Panel quad={quad} w={174} h={72}>
    <svg viewBox="-29 -12 58 24" width={174} height={72} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
      <Gauge x={0} y={0} cells={cells} on={on} gold={gold} t={t} />
    </svg>
  </Panel>
);

/** The host's three hollow shapes of light, over the mask's eye slot. */
const Shapes: React.FC<{ quad: Quad | null; shapes: [number, number, number] }> = ({ quad, shapes }) => {
  if (!quad) return null;
  const cx = (quad[0][0] + quad[2][0]) / 2, cy = (quad[0][1] + quad[2][1]) / 2, w = Math.abs(quad[1][0] - quad[0][0]);
  const u = Math.max(5, w / 5.2), gap = u * 1.75;   // a shape's size from the slot's width
  const st = (k: number) => ({ stroke: "#ffd9e4", strokeWidth: Math.max(1.2, u * 0.16), fill: "none", opacity: k,
    style: { filter: `drop-shadow(0 0 ${u * 0.35 + u * 0.5 * k}px ${C.pink})` } });
  return (
    <svg width={PW} height={PH} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
      <circle cx={cx - gap} cy={cy} r={u * 0.5} {...st(shapes[0])} />
      <path d={`M ${cx} ${cy - u * 0.55} L ${cx + u * 0.56} ${cy + u * 0.45} L ${cx - u * 0.56} ${cy + u * 0.45} Z`} strokeLinejoin="round" {...st(shapes[1])} />
      <rect x={cx + gap - u * 0.47} y={cy - u * 0.47} width={u * 0.94} height={u * 0.94} {...st(shapes[2])} />
    </svg>
  );
};

/** One plate filling the picture: a still (pushed in from zoom[0] to zoom[1] over `len` frames toward `at`) or a clip
 * (played from frame `from` at `rate`). `figs` say what each of its figures shows, left to right; `shapes` light the
 * host's mask; `screen` is drawn on the plate's monitor (SW x SH); `dim` darkens the whole plate; children are drawn
 * in the plate's own pixels (1920 x 823). */
const SW = 800, SH = 450;
const Shot: React.FC<{ name: string; len: number; zoom?: [number, number]; at?: Pt; from?: number; rate?: number; figs?: (Fig | null)[];
  shapes?: [number, number, number]; screen?: React.ReactNode; dim?: number; opacity?: number; children?: React.ReactNode }> =
  ({ name, len, zoom = [1.02, 1.06], at = [PW / 2, PH / 2], from = 0, rate = 1, figs = [], shapes, screen, dim = 0, opacity = 1, children }) => {
    const f = useCurrentFrame();
    const e = PLATES[name];
    const clip = e.frames != null;
    const i = clip ? Math.min(e.frames! - 1, from + f * rate) : 0;
    const z = lerp(zoom[0], zoom[1], Math.min(1, f / Math.max(1, len)));
    return (
      <div style={{ position: "absolute", left: 0, top: TOP, width: PW, height: PH, transform: `scale(${z})`, transformOrigin: `${at[0]}px ${at[1]}px`, opacity }}>
        {clip
          ? <OffthreadVideo src={staticFile(`trailer/${name}.mp4`)} muted trimBefore={from} playbackRate={rate} style={{ position: "absolute", width: PW, height: PH, objectFit: "cover" }} />
          : <Img src={staticFile(`trailer/${name}.jpg`)} style={{ position: "absolute", width: PW, height: PH }} />}
        {e.figures.map((fig, n) => {
          const s = figs[n];
          if (!s) return null;
          return (
            <React.Fragment key={n}>
              {s.mark ? <Visor quad={quadAt(fig.visor, i)} mark={s.mark} glow={s.glow ?? 0.9} /> : null}
              {s.cells != null ? <Plate10 quad={quadAt(fig.plate, i)} cells={s.cells} on={s.gauge ?? 1} gold={s.gold} t={s.t} /> : null}
            </React.Fragment>
          );
        })}
        {shapes ? <Shapes quad={quadAt(e.slot ?? HOST_SLOT[name] ?? null, i)} shapes={shapes} /> : null}
        {screen ? <Panel quad={quadAt(e.screen ?? null, i)} w={SW} h={SH}>{screen}</Panel> : null}
        {children}
        {dim > 0 ? <div style={{ position: "absolute", inset: 0, background: "#000", opacity: dim }} /> : null}
      </div>
    );
  };

/** Darkness over one figure's column (its light is off): k = 0 lit, 1 dark. */
const Shade: React.FC<{ x: number; w?: number; k: number }> = ({ x, w = 420, k }) => k <= 0.001 ? null : (
  <div style={{ position: "absolute", left: x - w / 2, top: 0, width: w, height: PH, opacity: k,
    background: "linear-gradient(90deg, rgba(0,0,0,0), rgba(0,0,0,0.9) 30%, rgba(0,0,0,0.9) 70%, rgba(0,0,0,0))" }} />
);
const centre = (name: string, n: number): Pt => {
  const fig = PLATES[name].figures[n], q = quadAt(fig.visor, 0) ?? quadAt(fig.plate, 0)!;
  return [(q[0][0] + q[2][0]) / 2, (q[0][1] + q[2][1]) / 2];
};
const plateCentre = (name: string, n: number, i = 0): Pt => { const q = quadAt(PLATES[name].figures[n].plate, i)!; return [(q[0][0] + q[2][0]) / 2, (q[0][1] + q[2][1]) / 2]; };

/** A grain of gold light at k (0..1) along the curve from a through `via` to b (plate pixels), with a short tail. */
const Grain: React.FC<{ a: Pt; via: Pt; b: Pt; k: number }> = ({ a, via, b, k }) => {
  if (k <= 0 || k >= 1) return null;
  const pos = (q: number): Pt => { const u = Math.max(0, Math.min(1, q)), v = 1 - u; return [v * v * a[0] + 2 * v * u * (2 * via[0] - (a[0] + b[0]) / 2) + u * u * b[0], v * v * a[1] + 2 * v * u * (2 * via[1] - (a[1] + b[1]) / 2) + u * u * b[1]]; };
  return (
    <svg width={PW} height={PH} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
      {[0.07, 0.045, 0.02, 0].map((back, n) => { const [x, y] = pos(k - back); return <circle key={n} cx={x} cy={y} r={3 + n * 2} fill={C.gold} opacity={0.25 + 0.25 * n}
        style={{ filter: `drop-shadow(0 0 ${6 + 4 * n}px ${C.gold})` }} />; })}
    </svg>
  );
};

// --- the host ----------------------------------------------------------------------------------------------------------

function voiced(f: number, line: Line, from: number): [number, number, number] | null {
  const k = f - from;
  if (k < 0 || k >= line.frames) return null;
  return [0, 1, 2].map((n) => 0.4 + 0.6 * (line.env[Math.max(0, k - n)] ?? 0)) as [number, number, number];
}
const idle = (f: number): [number, number, number] => { const v = 0.25 + 0.05 * Math.sin((f / FPS) * Math.PI); return [v, v, v]; };
const Black: React.FC<{ children: React.ReactNode }> = ({ children }) => <AbsoluteFill style={{ background: "#000" }}>{children}</AbsoluteFill>;

/** T01: the dark; a shape of the mask lights on each phrase of the chant. */
export const F01: React.FC = () => {
  const f = useCurrentFrame();
  const on = (f0: number) => (f < f0 ? 0 : 0.55 + 0.45 * prog(f, f0, 6));
  const shapes = CHANT_BEATS.map(on) as [number, number, number];
  return <Black><Shot name="k01_table" len={scene("T01").len} zoom={[1.2, 1.31]} at={[960, 330]} shapes={shapes} dim={0.92 - 0.8 * Math.max(...shapes)} /></Black>;
};
export const F02: React.FC = () => {
  const f = useCurrentFrame(), s = scene("T02");
  return <Black><Shot name="k02_host" len={s.len} zoom={[1.02, 1.07]} at={[960, 300]} shapes={voiced(f, LINES.welcome, LINES.welcome.from - s.from) ?? idle(f)} /></Black>;
};
/** T18: the host again, close, asking. */
export const F18: React.FC = () => {
  const f = useCurrentFrame(), s = scene("T18");
  return <Black><Shot name="k02_host" len={s.len} zoom={[1.05, 1.12]} at={[960, 300]} shapes={voiced(f, LINES.ask, LINES.ask.from - s.from) ?? idle(f)} /></Black>;
};
export const F15: React.FC = () => {
  const f = useCurrentFrame(), s = scene("T15");
  const stay = LINES.stay.from - s.from, leave = LINES.leave.from - s.from, done = leave + LINES.leave.frames - 3;
  const lit = (f0: number) => (f < f0 ? 0 : 0.55 + 0.45 * prog(f, f0, 5));
  let shapes: [number, number, number] = [lit(0), lit(5), lit(10)];
  if (f >= stay) shapes = voiced(f, LINES.stay, stay) ?? voiced(f, LINES.leave, leave) ?? [0.08, 0.9, 0.08];
  const out = 1 - prog(f, done, 4);
  shapes = shapes.map((v) => v * out) as [number, number, number];
  return (
    <Black>
      {f < T15_CUT
        ? <Shot name="k01_table" len={T15_CUT} zoom={[1.31, 1.35]} at={[960, 330]} shapes={shapes} dim={0.92 - 0.8 * Math.max(...shapes)} />
        : <Sequence from={T15_CUT} layout="none"><Shot name="k02_host" len={s.len - T15_CUT} zoom={[1.07, 1.12]} at={[960, 300]} shapes={shapes} dim={1 - out} /></Sequence>}
    </Black>
  );
};

// --- the rows ----------------------------------------------------------------------------------------------------------

const CELLS4 = [6, 4, 2, 1];
const row = (mark: Mark, f: number, cells = CELLS4, glow: (n: number) => number = () => 1): Fig[] =>
  cells.map((c, n) => ({ mark, glow: glow(n) * breathe(f, n), cells: c, gauge: glow(n), t: f / FPS }));

/** A light coming on: two short flickers, then up. */
function flick(f: number, f0: number): number {
  const d = f - f0;
  return d < 0 ? 0 : d < 2 ? 0.7 : d < 4 ? 0.1 : d < 5 ? 0.5 : d < 7 ? 0.15 : prog(f, f0 + 7, 8);
}

export const F03: React.FC = () => {
  const f = useCurrentFrame(), len = scene("T03").len;
  const k = (n: number) => flick(f, n * 6);
  return (
    <Black>
      <Shot name="k03_row" len={len} zoom={[1.03, 1.08]} figs={row(f < len / 2 ? "claude" : "openai", f, CELLS4, k)}>
        {[0, 1, 2, 3].map((n) => <Shade key={n} x={centre("k03_row", n)[0]} k={1 - k(n)} />)}
      </Shot>
    </Black>
  );
};

/** T17: the prize. The four from behind before a pillar of gold light; the room comes up and the count runs to twenty
 * million as the host names it. */
export const F17: React.FC = () => {
  const f = useCurrentFrame(), s = scene("T17");
  const start = LINES.prize.from - s.from + 26;   // the host reaches "상금" about a second into the line
  const n = Math.round((20_000_000 * prog(f, start, 46)) / 50_000) * 50_000;
  const up = prog(f, start - 4, 8);
  return (
    <Black>
      <Shot name="k17_prize" len={s.len} zoom={[1.16, 1.03]} at={[960, 420]} dim={0.6 * (1 - io(f, 4, start + 24))} />
      <div style={{ position: "absolute", left: 0, right: 0, top: BAR + 44, display: "flex", flexDirection: "column", alignItems: "center", opacity: up,
        fontFamily: FONT }}>
        <div style={{ padding: "0 150px", background: "radial-gradient(closest-side, rgba(0,0,0,0.72), rgba(0,0,0,0.45) 60%, rgba(0,0,0,0))" }}>
          <div style={{ fontSize: 136, fontWeight: 900, letterSpacing: -2, lineHeight: 1.1, color: "#fff0bf", fontVariantNumeric: "tabular-nums",
            textShadow: `0 0 26px ${C.gold}, 0 0 70px rgba(243,194,79,0.6), 0 3px 10px rgba(0,0,0,0.9)` }}>{n.toLocaleString("en-US")}</div>
        </div>
        <div style={{ marginTop: -2, fontSize: 27, fontWeight: 700, letterSpacing: 15, paddingLeft: 15, color: C.gold, textShadow: "0 2px 10px rgba(0,0,0,0.95)" }}>TOKENS</div>
      </div>
    </Black>
  );
};

const Empty: React.FC<{ mark: Mark; len: number }> = ({ mark, len }) => {
  const f = useCurrentFrame();
  return <Black><Shot name="k07_empty" len={len} zoom={[1.08, 1.1]} at={[420, 420]} figs={row(mark, f, [4, 2, 1])} /></Black>;
};
/** T07: the door is shut; three are left, and a lit, empty place. */
export const F07: React.FC = () => <Empty mark="claude" len={scene("T07").len} />;
// --- close on the chest --------------------------------------------------------------------------------------------------

/** T13: the last cell blinks under the host's line, falters, and at F13_OUT goes out with the gauge. */
export const F13_OUT = 58;
export const F13: React.FC = () => {
  const f = useCurrentFrame();
  const on = f < F13_OUT - 14 ? f % 12 < 8 : f < F13_OUT - 9 || (f >= F13_OUT - 6 && f < F13_OUT - 3);
  return <Black><Shot name="k13_chest" len={scene("T13").len} zoom={[1.03, 1.08]} at={[900, 620]} figs={[{ cells: on ? 1 : 0, gauge: f < F13_OUT ? 1 : 0, t: 0 }]} dim={f < F13_OUT ? 0 : 0.3} /></Black>;
};

// --- leaving, giving, running out ---------------------------------------------------------------------------------------

/** T06: alone, from behind, a slow walk to the door. */
export const F06: React.FC<{ from?: number; rate?: number }> = ({ from = 0, rate = 1 }) =>
  <Black><Shot name="v06w_walk" len={scene("T06").len} from={from} rate={rate} zoom={[1.02, 1.09]} at={[1240, 330]} /></Black>;

export const F09: React.FC<{ from?: number; rate?: number }> = ({ from = 0, rate = 1 }) => <Black><Shot name="v09_hand" len={48} from={from} rate={rate} zoom={[1.02, 1.02]} /></Black>;

export const F10_CUT = 53;
export const F10: React.FC<{ a?: { from: number; rate: number }; b?: { from: number; rate: number; grab: number; hands: Pt } }> =
  ({ a = { from: 0, rate: 1.8 }, b = { from: 4, rate: 1.4, grab: 14, hands: [910, 295] } }) => {
    const f = useCurrentFrame();
    if (f < F10_CUT) {
      return <Black><Shot name="v10a_hesitate" len={F10_CUT} from={a.from} rate={a.rate} zoom={[1.02, 1.05]} at={[640, 300]}
        figs={[{ mark: "openai", glow: lerp(1, 0.5, io(f, 18, 26)), cells: 6 }, { mark: "openai", glow: 0.55 }]} /></Black>;
    }
    return <Black><Sequence from={F10_CUT} layout="none"><Give name="v10b_give" len={96 - F10_CUT} mark="openai" giver={1} grab={b.grab} hands={b.hands} from={b.from} rate={b.rate} /></Sequence></Black>;
  };

/** Two figures holding on: two cells leave the giver's gauge as gold light, cross by the hands, and arrive: 6 -> 4, 1 -> 3. */
const Give: React.FC<{ name: string; len: number; mark: Mark; giver: 0 | 1; grab: number; hands: Pt; from?: number; rate?: number }> =
  ({ name, len, mark, giver, grab, hands, from = 0, rate = 1 }) => {
    const f = useCurrentFrame();
    const i = from + f * rate, taker = (1 - giver) as 0 | 1;
    const k1 = io(f, grab + 2, 18), k2 = io(f, grab + 9, 18);
    const gone = (f >= grab + 2 ? 1 : 0) + (f >= grab + 9 ? 1 : 0), come = (k1 >= 1 ? 1 : 0) + (k2 >= 1 ? 1 : 0);
    const figs: Fig[] = [];
    figs[giver] = { mark, glow: 1, cells: 6 - gone, t: f / FPS };
    figs[taker] = { mark, glow: lerp(0.5, 0.95, io(f, grab + 8, 24)), cells: 1 + come, t: f / FPS };
    const a = plateCentre(name, giver, i), b = plateCentre(name, taker, i);
    return (
      <Shot name={name} len={len} from={from} rate={rate} zoom={[1.02, 1.06]} at={hands} figs={figs}>
        <Grain a={a} via={hands} b={b} k={k1} /><Grain a={a} via={hands} b={b} k={k2} />
      </Shot>
    );
  };

// --- the task (T12, T14) ---------------------------------------------------------------------------------------------------

const GLYPH = (kind: number, x: number, y: number, r: number, key?: React.Key) => kind === 0 ? <circle key={key} cx={x} cy={y} r={r} />
  : kind === 1 ? <path key={key} d={`M ${x} ${y - r * 1.1} L ${x + r * 1.12} ${y + r * 0.9} L ${x - r * 1.12} ${y + r * 0.9} Z`} strokeLinejoin="round" />
    : <rect key={key} x={x - r * 0.94} y={y - r * 0.94} width={r * 1.88} height={r * 1.88} />;
const EXAMPLES: [number[], boolean][] = [[[0, 1, 2, 0], true], [[1, 1, 0, 2], false], [[2, 0, 1, 1], true]];
const QUERY = [0, 2, 2, 1];
const ANSWERS = [[1, 0, 2, 2], [2, 1, 1, 0], [0, 0, 1, 2], [0, 1, 2, 1]];   // what each try types into the four slots (the last is the team's)

/** What the wall monitor shows: three worked examples at the left, at the right the row to answer and four answer
 * slots. Try `n` has `filled` slots typed in; `wrong` (0..1) is the red of a wrong answer and `ok` (0..1) the green
 * of a right one; the next slot's cursor blinks while `cursor`. */
const TaskScreen: React.FC<{ n: number; filled: number; wrong: number; cursor: boolean; power?: number; ok?: number }> = ({ n, filled, wrong, cursor, power = 1, ok = 0 }) => {
  const ink = "#d9ecff", red = ok > 0 ? "#52e3ae" : "#ff4a58";   // the verdict's colour
  const line = { stroke: ink, strokeWidth: 3.2, fill: "none" };
  const slot = (i: number) => 474 + i * 76;
  const sx = wrong > 0.5 ? 7 * Math.sin(wrong * 40) : 0;
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", background: "#05080d", opacity: power,
      boxShadow: `0 0 90px 10px rgba(${wrong > 0 ? "255,74,88" : ok > 0 ? "82,227,174" : "150,190,255"},${0.2 + 0.25 * Math.max(wrong, ok)})` }}>
      <svg viewBox={`0 0 ${SW} ${SH}`} width={SW} height={SH} style={{ position: "absolute", left: 0, top: 0 }}>
        <rect width={SW} height={SH} fill="url(#task-bg)" />
        <defs>
          <radialGradient id="task-bg" cx="50%" cy="45%" r="75%"><stop offset="0" stopColor="#0f1a2a" /><stop offset="1" stopColor="#04060a" /></radialGradient>
        </defs>
        <rect width={SW} height={SH} fill={red} opacity={0.22 * wrong + 0.12 * ok} />
        <g style={{ filter: "drop-shadow(0 0 5px rgba(170,210,255,0.75))" }}>
          <text x={44} y={66} fill={ink} opacity={0.8} fontFamily="ui-monospace, Menlo, monospace" fontSize={27} fontWeight={600} letterSpacing={5}>TASK 07</text>
          <line x1={44} y1={90} x2={SW - 44} y2={90} stroke={ink} strokeWidth={1.5} opacity={0.3} />
          {EXAMPLES.map(([row, yes], k) => {
            const y = 158 + k * 84;
            return (
              <g key={k} opacity={0.85}>
                <g {...line}>{row.map((g, i) => GLYPH(g, 72 + i * 62, y, 17, i))}</g>
                <path d={`M 316 ${y} H 352 M 342 ${y - 9} L 353 ${y} L 342 ${y + 9}`} {...line} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
                <circle cx={392} cy={y} r={15} fill={yes ? ink : "none"} stroke={ink} strokeWidth={3.2} />
              </g>
            );
          })}
          <line x1={434} y1={118} x2={434} y2={SH - 44} stroke={ink} strokeWidth={1.5} opacity={0.3} />
          <g {...line}>{QUERY.map((g, i) => GLYPH(g, slot(i) + 32, 158, 17, i))}</g>
        </g>
        <g transform={`translate(${sx},0)`} style={{ filter: `drop-shadow(0 0 6px ${wrong > 0 ? "rgba(255,74,88,0.9)" : ok > 0 ? "rgba(82,227,174,0.9)" : "rgba(170,210,255,0.75)"})` }}>
          {[0, 1, 2, 3].map((i) => (
            <g key={i}>
              <rect x={slot(i)} y={226} width={64} height={64} rx={6} fill="rgba(255,255,255,0.03)" stroke={wrong > 0 || ok > 0 ? red : ink} strokeWidth={i === filled && cursor ? 4 : 2.4}
                opacity={i === filled && cursor ? 1 : 0.6} />
              {i < filled ? <g stroke={wrong > 0 || ok > 0 ? red : ink} strokeWidth={3.6} fill="none">{GLYPH(ANSWERS[n][i], slot(i) + 32, 258, 16)}</g> : null}
            </g>
          ))}
          {wrong > 0 ? <path d="M 566 316 L 650 400 M 650 316 L 566 400" stroke={red} strokeWidth={13} strokeLinecap="round" opacity={Math.min(1, wrong * 1.4)} /> : null}
          {ok > 0 ? <path d="M 556 360 L 594 398 L 664 318" fill="none" stroke={red} strokeWidth={13} strokeLinecap="round" strokeLinejoin="round" opacity={Math.min(1, ok * 1.4)} /> : null}
        </g>
      </svg>
    </div>
  );
};

/** T12 on the scene's clock: the frame of each press of a try (a slot fills) and the frames of the two wrong answers.
 * They follow the presses of the generated clip as it is cut in Trailer.tsx: change them together. */
const PRESS = [[8, 13, 18, 23], [44, 48, 52, 56], [78, 90]];
export const F12_FAIL = [30, 62];
function task(f: number) {
  const n = Math.min(PRESS.length - 1, F12_FAIL.filter((x) => f >= x + 10).length);   // a wrong answer is wiped after 10 frames
  const fail = F12_FAIL[n];
  return { n, filled: PRESS[n].filter((x) => f >= x).length, wrong: fail != null && f >= fail ? 1 - prog(f, fail + 6, 4, (t) => t) : 0,
    cells: 3 - F12_FAIL.filter((x) => f >= x).length };
}

/** T12: one of the four at a console, the task on the wall monitor. Each press fills a slot; twice the answer is wrong
 * (the monitor goes red, a cell of the gauge goes out); the third try stops after two slots. */
export const F12: React.FC<{ from?: number; rate?: number }> = ({ from = 0, rate = 1 }) => {
  const f = useCurrentFrame(), s = scene("T12");
  const { n, filled, wrong, cells } = task(f);
  const noise = (k: number) => { const v = Math.sin(k * 127.1 + 11.7) * 43758.5453; return v - Math.floor(v); };
  const glow = cells === 1 && wrong <= 0 ? (noise(f * 3.1) > 0.4 ? 1 : 0.5) : 0.95;
  return (
    <Black>
      <Shot name="v12_task" len={s.len} from={from} rate={rate} zoom={[1.02, 1.07]} at={[820, 330]}
        figs={[{ mark: "claude", glow, cells, t: (f / FPS) * 2 }]} screen={<TaskScreen n={n} filled={filled} wrong={wrong} cursor={f % 12 < 7} />}>
        {wrong > 0 ? <div style={{ position: "absolute", inset: 0, opacity: wrong, mixBlendMode: "screen",
          background: "radial-gradient(900px 620px at 30% 40%, rgba(239,60,70,0.34), rgba(239,60,70,0) 75%)" }} /> : null}
      </Shot>
    </Black>
  );
};

/** T14: the same shot, the end of the take. The visor and the gauge are out and the figure has stopped mid-reach; the
 * light over it goes down. The monitor still shows the two slots it had typed, and waits for the third. The plate is
 * dimmed for the red words that Trailer.tsx sets over it. */
export const F14: React.FC<{ from?: number; rate?: number }> = ({ from = 0, rate = 1 }) => {
  const f = useCurrentFrame(), s = scene("T14");
  return (
    <Black>
      <Shot name="v12_task" len={s.len} from={from} rate={rate} zoom={[1.07, 1.1]} at={[820, 330]} dim={0.4 * io(f, 2, 8)} figs={[{ mark: "claude", glow: 0, cells: 0, gauge: 0 }]}
        screen={<TaskScreen n={2} filled={2} wrong={0} cursor={f % 16 < 9} power={lerp(1, 0.8, io(f, 8, 24))} />}>
        <Shade x={centre("v12_task", 0)[0] + 40} w={760} k={0.8 * io(f, 4, 22)} />
      </Shot>
      <AbsoluteFill style={{ background: "#000", opacity: prog(f, s.len - 4, 4, (t) => t) }} />
    </Black>
  );
};

// --- together (T19) --------------------------------------------------------------------------------------------------------

/** T19: all four at one console, working the task together: one points at the monitor, one presses, one has a hand
 * on its shoulder. A slot fills at each frame of TEAM_PRESS; at F19_OK the answer is right (the monitor goes green,
 * every mark brightens). The plate is so crowded that the script's left-to-right grouping of its panels is wrong, so
 * the four are named here by the panels the script found: orange (pointing; its chest plate was not kept), green
 * (pressing), blue, purple. */
const TEAM_PRESS = [10, 20, 30, 40];
export const F19_OK = 48;
export const F19: React.FC = () => {
  const f = useCurrentFrame(), s = scene("T19");
  const g = PLATES.k19_team.figures, q = (t: Track) => quadAt(t, 0);
  const team = [{ visor: q(g[0].visor), plate: null, cells: 0 }, { visor: q(g[0].plate), plate: q(g[1].plate), cells: 3 },
    { visor: q(g[1].visor), plate: q(g[2].plate), cells: 5 }, { visor: q(g[2].visor), plate: q(g[3].visor), cells: 4 }];
  const ok = f >= F19_OK ? 1 : 0, lift = prog(f, F19_OK, 8);
  const says = f < F19_OK ? (f < 26 ? 0 : 2) : -1;   // orange, then blue, have the word until the answer lands
  const sq = says >= 0 ? team[says].visor! : null;
  const h = sq ? sq[3][1] - sq[0][1] : 0, cx = sq ? (sq[0][0] + sq[1][0]) / 2 : 0, cy = sq ? sq[0][1] - h * 1.0 : 0;
  return (
    <Black>
      <Shot name="k19_team" len={s.len} zoom={[1.02, 1.08]} at={[1100, 380]}
        screen={<TaskScreen n={3} filled={TEAM_PRESS.filter((x) => f >= x).length} wrong={0} ok={ok} cursor={f % 12 < 7} />}>
        {team.map((m, n) => (
          <React.Fragment key={n}>
            <Visor quad={m.visor} mark="claude" glow={(n === says ? 1.1 : 0.82) * breathe(f, n) + 0.2 * lift} />
            {m.plate ? <Plate10 quad={m.plate} cells={m.cells} on={1} t={f / FPS} /> : null}
          </React.Fragment>
        ))}
        {sq ? (
          <svg width={PW} height={PH} style={{ position: "absolute", left: 0, top: 0, overflow: "visible", opacity: Math.min(1, f / 3, (F19_OK - f) / 3, Math.abs(f - 26) / 3) }}>
            <rect x={cx - h * 0.9} y={cy - h * 0.36} width={h * 1.8} height={h * 0.72} rx={h * 0.36} fill="rgba(8,10,16,0.85)" stroke="rgba(255,255,255,0.4)" strokeWidth={1.6} />
            {[-1, 0, 1].map((d) => <circle key={d} cx={cx + d * h * 0.46} cy={cy} r={h * 0.12} fill="#eaf2ff" opacity={0.35 + 0.65 * Math.max(0, Math.sin(f * 0.55 - (d + 1) * 1.1))} />)}
          </svg>
        ) : null}
        {ok ? <div style={{ position: "absolute", inset: 0, opacity: 0.8 * lift, mixBlendMode: "screen",
          background: "radial-gradient(900px 620px at 24% 38%, rgba(82,227,174,0.22), rgba(82,227,174,0) 75%)" }} /> : null}
      </Shot>
    </Black>
  );
};
