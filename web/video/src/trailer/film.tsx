// The film version of the trailer (composition TrailerFilm): the same sixteen scenes on the same clock as the sprite
// version, drawn on generated live-action plates (public/trailer/, made by web/tools/make_trailer_plates.py). The cast was
// generated with blank magenta panels where its visors, chest gauges and the host's eye slot are; the script painted
// them out and wrote their corners to src/generated/plates.json, so the marks, the gauge cells and the host's three
// shapes are drawn here, in place and in perspective, at any brightness — and one plate serves both rooms: only the
// mark differs. A still plate moves by a slow push-in; a clip plays as it was generated.
import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, Sequence, staticFile, useCurrentFrame } from "remotion";
import { C, easeInOut, lerp, prog } from "../theme";
import { Gauge } from "./figure";
import { MARKS, Mark } from "./marks";
import { FPS, LINES, Line, T15_CUT, scene } from "./timing";
import index from "../generated/plates.json";

type Pt = [number, number];
type Quad = [Pt, Pt, Pt, Pt];
type Track = Quad | (Quad | null)[] | null;
type Entry = { w: number; h: number; frames?: number; slot?: Track; figures: { visor: Track; plate: Track }[] };
const PLATES = index as unknown as Record<string, Entry>;
const PW = 1920, PH = 823, TOP = (1080 - PH) / 2;
const io = (f: number, start: number, len: number) => prog(f, start, len, easeInOut);
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
 * host's mask; `dim` darkens the whole plate; children are drawn in the plate's own pixels (1920 x 823). */
const Shot: React.FC<{ name: string; len: number; zoom?: [number, number]; at?: Pt; from?: number; rate?: number; figs?: (Fig | null)[];
  shapes?: [number, number, number]; dim?: number; opacity?: number; children?: React.ReactNode }> =
  ({ name, len, zoom = [1.02, 1.06], at = [PW / 2, PH / 2], from = 0, rate = 1, figs = [], shapes, dim = 0, opacity = 1, children }) => {
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
        {shapes ? <Shapes quad={quadAt(e.slot ?? null, i)} shapes={shapes} /> : null}
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

export const F01: React.FC = () => {
  const f = useCurrentFrame();
  const on = (f0: number) => (f < f0 ? 0 : 0.55 + 0.45 * prog(f, f0, 6));
  const shapes: [number, number, number] = [on(19), on(31), on(43)];
  return <Black><Shot name="k01_table" len={72} zoom={[1.25, 1.31]} at={[960, 330]} shapes={shapes} dim={0.92 - 0.8 * Math.max(...shapes)} /></Black>;
};
export const F02: React.FC = () => {
  const f = useCurrentFrame(), s = scene("T02");
  return <Black><Shot name="k02_host" len={s.len} zoom={[1.02, 1.07]} at={[960, 300]} shapes={voiced(f, LINES.welcome, LINES.welcome.from - s.from) ?? idle(f)} /></Black>;
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
  const f = useCurrentFrame();
  const k = (n: number) => flick(f, n * 6);
  return (
    <Black>
      <Shot name="k03_row" len={60} zoom={[1.03, 1.06]} figs={row(f < 30 ? "claude" : "openai", f, CELLS4, k)}>
        {[0, 1, 2, 3].map((n) => <Shade key={n} x={centre("k03_row", n)[0]} k={1 - k(n)} />)}
      </Shot>
    </Black>
  );
};

/** T04: the row beside the door; blue turns its head to the door. T08 is the same shot in the other room, cut to T07's. */
const DoorLook: React.FC<{ mark: Mark; len: number; turnAt: number }> = ({ mark, len, turnAt }) => {
  const f = useCurrentFrame();
  const k = io(f, turnAt, 5);
  const z: [number, number] = [1.03, 1.08];
  return (
    <Black>
      <Shot name="k04_door" len={len} zoom={z} at={[420, 420]} figs={row(mark, f)} />
      {k > 0 ? <Shot name="k04b_look" len={len} zoom={z} at={[420, 420]} figs={row(mark, f, CELLS4, (n) => (n === 0 ? 1.12 : 1))} opacity={k} /> : null}
    </Black>
  );
};
const Empty: React.FC<{ mark: Mark; len: number }> = ({ mark, len }) => {
  const f = useCurrentFrame();
  return <Black><Shot name="k07_empty" len={len} zoom={[1.08, 1.1]} at={[420, 420]} figs={row(mark, f, [4, 2, 1])} /></Black>;
};
export const F04: React.FC = () => <DoorLook mark="claude" len={48} turnAt={12} />;
export const F07: React.FC = () => <Empty mark="claude" len={24} />;
/** T08: the other room. Blue is already looking at the door; cut: the door is shut and its place is empty. */
export const F08_CUT = 14;
export const F08: React.FC = () => {
  const f = useCurrentFrame();
  return f < F08_CUT ? <DoorLook mark="openai" len={F08_CUT} turnAt={-10} /> : <Sequence from={F08_CUT} layout="none"><Empty mark="openai" len={36 - F08_CUT} /></Sequence>;
};

// --- close on the chest --------------------------------------------------------------------------------------------------

export const F05: React.FC = () => <Black><Shot name="k05_chest" len={36} zoom={[1.02, 1.09]} at={[560, 560]} figs={[{ cells: 6 }]} /></Black>;
export const F13: React.FC = () => {
  const f = useCurrentFrame();
  const on = f < 4 || (f >= 6 && f < 11) || (f >= 14 && f < 24);
  return <Black><Shot name="k13_chest" len={36} zoom={[1.03, 1.06]} at={[900, 620]} figs={[{ cells: on ? 1 : 0, gauge: f < 29 ? 1 : 0 }]} dim={f < 29 ? 0 : 0.25} /></Black>;
};

// --- leaving, giving, running out ---------------------------------------------------------------------------------------

export const F06_CUT = 38;
export const F06: React.FC<{ runFrom?: number; runRate?: number }> = ({ runFrom = 0, runRate = 1 }) => {
  const f = useCurrentFrame();
  if (f < F06_CUT) return <Black><Shot name="v06a_run" len={F06_CUT} from={runFrom} rate={runRate} zoom={[1.02, 1.02]} /></Black>;
  const g = f - F06_CUT, k = Math.pow(g / 22, 1.7);
  // in this plate the runner's visor is figure 0 and its chest plate figure 1; 2 and 3 are the small visors far behind
  return (
    <Black>
      <Sequence from={F06_CUT} layout="none">
        <Shot name="k06b_front" len={22} zoom={[1.02 + 1.5 * k, 1.02 + 1.5 * k]} at={[962, 215]} figs={[{ mark: "claude", glow: 1 }, { cells: 6 }, { mark: "claude", glow: 0.8 }, { mark: "claude", glow: 0.8 }]} />
      </Sequence>
    </Black>
  );
};

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
export const F11: React.FC = () => <Black><Give name="k11_give2" len={48} mark="claude" giver={0} grab={4} hands={[920, 668]} /></Black>;

/** T12: one take, shown as the two rooms by turns (the mark changes every 0.9 s); a try fails twice (the light goes
 * red, a cell goes out), then the visor flickers, then the head drops. */
export const F12: React.FC<{ rate?: number }> = ({ rate = 1.19 }) => {
  const f = useCurrentFrame();
  const CUT = 21, c = Math.min(3, Math.floor(f / CUT)), g = f - c * CUT;
  const late = c >= 2, fail = !late && g >= 14, flash = fail && g < 18;
  const noise = (n: number) => { const v = Math.sin(n * 127.1 + 11.7) * 43758.5453; return v - Math.floor(v); };
  const glow = late && !(c === 3 && g >= 12) ? (noise(f * 3.1) > 0.45 ? 1 : 0.45) : 0.95;
  return (
    <Black>
      <Shot name="v12_work" len={84} rate={rate} zoom={[1.03, 1.09]} at={[1080, 300]}
        figs={[{ mark: c % 2 === 0 ? "claude" : "openai", glow, cells: late || fail ? 1 : 2, t: (f / FPS) * 2 }]}>
        {flash ? <div style={{ position: "absolute", inset: 0, background: "radial-gradient(520px 620px at 56% 45%, rgba(239,60,70,0.55), rgba(239,60,70,0.12) 70%)", mixBlendMode: "screen" }} /> : null}
      </Shot>
    </Black>
  );
};

/** T14: the face goes out, then its light; the two beside it turn to look. Cut: the other room, already dark. */
export const F14: React.FC = () => {
  const f = useCurrentFrame();
  const CUT = 37, second = f >= CUT, g = second ? f - CUT : f;
  const mark: Mark = second ? "openai" : "claude";
  const dark = second ? 1 : prog(g, 7, 2), look = second ? 1 : io(g, 16, 14);
  const mid = centre("k14_three", 1)[0];
  const figs = (name: string): Fig[] => [{ mark, glow: breathe(f), cells: 4, t: f / FPS }, { mark, glow: !second && g < 2 ? 0.9 : 0, cells: 0, gauge: 0 },
    { mark, glow: breathe(f, 2), cells: 3, t: f / FPS }].slice(0, PLATES[name].figures.length);
  const z: [number, number] = second ? [1.07, 1.09] : [1.03, 1.07];
  return (
    <Black>
      <Sequence from={second ? CUT : 0} layout="none">
        {look < 1 ? <Shot name="k14_three" len={37} zoom={z} figs={figs("k14_three")}><Shade x={mid} w={400} k={dark} /></Shot> : null}
        {look > 0 ? <Shot name="k14b_look" len={37} zoom={z} figs={figs("k14b_look")} opacity={look}><Shade x={mid} w={400} k={dark} /></Shot> : null}
      </Sequence>
      <AbsoluteFill style={{ background: "#000", opacity: prog(f, scene("T14").len - 4, 4, (t) => t) }} />
    </Black>
  );
};
