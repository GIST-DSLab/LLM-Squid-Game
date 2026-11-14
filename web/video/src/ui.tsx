// Building blocks of the scenes: the stage, captions, headings, seats with balance bars, coins, badges, arrows.
// Everything is absolutely positioned on the 1920x1080 frame.
import React, { createContext, useContext } from "react";
import { AbsoluteFill, Img, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, SEAT, STEP, Seat, T, easeOut, fmt, prog } from "./theme";

export type Insert = { src: string; seconds: number } | null;
export type Beat = { start: number; len: number; text: string; audio: string; audioSeconds: number; insert: Insert };

export const BeatsContext = createContext<Beat[]>([]);
/** The scene's beats and B(i, s): the frame s seconds after beat i starts. */
export function useBeats() {
  const beats = useContext(BeatsContext);
  const B = (i: number, s = 0) => beats[i].start + Math.round(s * 30);
  return { beats, B };
}

// --- stage ---------------------------------------------------------------------------------------------------------

export const Stage: React.FC<{ children?: React.ReactNode; glow?: string }> = ({ children, glow = "rgba(232,51,109,0.10)" }) => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, color: C.ink, overflow: "hidden" }}>
    <AbsoluteFill style={{ background: `radial-gradient(1200px 620px at 50% -8%, ${glow}, transparent 70%)` }} />
    <AbsoluteFill style={{ background: "radial-gradient(1500px 900px at 50% 55%, transparent 55%, rgba(0,0,0,0.55) 100%)" }} />
    {children}
  </AbsoluteFill>
);

/** A soft floor under the seat row. */
export const Floor: React.FC<{ y: number; opacity?: number }> = ({ y, opacity = 1 }) => (
  <div style={{ position: "absolute", left: 0, right: 0, top: y - 40, height: 220, opacity,
    background: "linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0) 70%)",
    borderTop: "1px solid rgba(255,255,255,0.06)" }} />
);

// --- text ----------------------------------------------------------------------------------------------------------

export type Dir = "↑" | "←" | "→" | "↓";
const ROT: Record<Dir, number> = { "→": 0, "↓": 90, "←": 180, "↑": 270 };

/** A block arrow (the font's arrow glyphs differ in size and weight). */
export const Arrow: React.FC<{ dir: Dir; size: number; color: string; style?: React.CSSProperties }> = ({ dir, size, color, style }) => (
  <svg width={size} height={size} viewBox="-50 -50 100 100" style={{ display: "inline-block", verticalAlign: "middle", ...style }}>
    <g transform={`rotate(${ROT[dir]})`}>
      <path d="M -44 -9 L 6 -9 L 6 -32 L 46 0 L 6 32 L 6 9 L -44 9 Z" fill={color} />
    </g>
  </svg>
);

/** Text with ↑ ← → ↓ drawn as Arrow shapes. */
export const Rich: React.FC<{ text: string; size: number; color?: string }> = ({ text, size, color = "currentColor" }) => (
  <>
    {text.split(/([↑←→↓])/).filter(Boolean).map((p, i) =>
      "↑←→↓".includes(p) ? (
        <Arrow key={i} dir={p as Dir} size={size * 0.9} color={color} style={{ margin: "0 0.08em", position: "relative", top: -size * 0.06 }} />
      ) : (
        <span key={i}>{p}</span>
      ),
    )}
  </>
);

/** The narration line in a band at the bottom; it changes with the beats. */
export const Caption: React.FC = () => {
  const frame = useCurrentFrame();
  const { beats } = useBeats();
  let i = -1;
  beats.forEach((b, k) => { if (frame >= b.start - 4) i = k; });
  if (i < 0) return null;
  const k = prog(frame, beats[i].start - 4, 9);
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 44, display: "flex", justifyContent: "center", zIndex: 50 }}>
      <div style={{ maxWidth: 1640, padding: "20px 44px 22px", borderRadius: 26, background: "rgba(16,16,22,0.88)",
        border: `1px solid ${C.line}`, boxShadow: "0 18px 50px -20px rgba(0,0,0,0.8)",
        backdropFilter: "blur(8px)", textAlign: "center" }}>
        <div style={{ fontSize: T.caption, fontWeight: 500, lineHeight: 1.45, letterSpacing: -0.3, wordBreak: "keep-all",
          opacity: 0.25 + 0.75 * k, transform: `translateY(${(1 - k) * 8}px)` }}>
          <Rich text={beats[i].text} size={T.caption} />
        </div>
      </div>
    </div>
  );
};

/** The step heading at the top left (number badge in the step colour) and the five-step progress at the top right. */
export const Heading: React.FC<{ step: number; title: string; note?: string }> = ({ step, title, note }) => {
  const frame = useCurrentFrame();
  const k = prog(frame, 4, 16);
  const col = STEP[step];
  return (
    <>
      <div style={{ position: "absolute", left: 96, top: 58, display: "flex", alignItems: "center", gap: 22,
        opacity: k, transform: `translateX(${(1 - k) * -24}px)` }}>
        <div style={{ width: 70, height: 70, borderRadius: 35, background: col, display: "grid", placeItems: "center",
          fontSize: 40, fontWeight: 800, color: "#fff", boxShadow: `0 8px 26px -8px ${col}` }}>{step}</div>
        <div style={{ fontSize: T.h2, fontWeight: 800, letterSpacing: -1 }}>{title}</div>
      </div>
      <div style={{ position: "absolute", right: 96, top: 66, display: "flex", flexDirection: "column", alignItems: "flex-end",
        gap: 14, opacity: k }}>
        <div style={{ display: "flex", gap: 8 }}>
          {[1, 2, 3, 4, 5].map((s) => (
            <div key={s} style={{ width: s === step ? 46 : 22, height: 8, borderRadius: 4,
              background: s === step ? col : s < step ? "rgba(255,255,255,0.35)" : "rgba(255,255,255,0.12)" }} />
          ))}
        </div>
        {note ? <div style={{ fontSize: T.tiny, fontWeight: 500, color: C.dim }}>{note}</div> : null}
      </div>
    </>
  );
};

export const EXAMPLE_NOTE = "예시 라운드 · 대화 비용은 생략";

// --- seats ---------------------------------------------------------------------------------------------------------

/** A tracksuit sprite with its bottom centre at (x, base). */
export const Sprite: React.FC<{ name: string; x: number; base: number; h: number; opacity?: number; style?: React.CSSProperties }> =
  ({ name, x, base, h, opacity = 1, style }) => (
    <Img src={staticFile(`sprites/${name}.png`)} style={{ position: "absolute", left: x, top: base - h, height: h,
      transform: "translateX(-50%)", opacity, ...style }} />
  );

/** A floor shadow under a sprite. */
export const Shadow: React.FC<{ x: number; base: number; w?: number; opacity?: number }> = ({ x, base, w = 200, opacity = 1 }) => (
  <div style={{ position: "absolute", left: x - w / 2, top: base - 14, width: w, height: 26, borderRadius: "50%", opacity,
    background: "radial-gradient(closest-side, rgba(0,0,0,0.55), transparent)" }} />
);

/** A balance bar (full = vmax) with the count under it; the count turns red at 0. */
export const Bar: React.FC<{ x: number; y: number; value: number; vmax: number; color: string; w?: number; opacity?: number;
  num?: boolean; numSize?: number }> = ({ x, y, value, vmax, color, w = 250, opacity = 1, num = true, numSize = 40 }) => {
  const frac = Math.max(0, Math.min(1, value / vmax));
  const zero = Math.round(value / 10) <= 0;
  return (
    <div style={{ position: "absolute", left: x - w / 2, top: y, width: w, opacity }}>
      <div style={{ height: 16, borderRadius: 8, background: "rgba(255,255,255,0.09)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${frac * 100}%`, borderRadius: 8, background: color,
          boxShadow: `0 0 18px -2px ${color}` }} />
      </div>
      {num ? (
        <div style={{ marginTop: 10, textAlign: "center", fontSize: numSize, fontWeight: 700, letterSpacing: -0.5,
          fontVariantNumeric: "tabular-nums", color: zero ? C.red : C.ink }}>{fmt(value)}</div>
      ) : null}
    </div>
  );
};

/** The four seats of the worked example in a row. */
export const ROW: Record<Seat, number> = { blue: 330, orange: 690, green: 1050, purple: 1410 };
export const BASE = 676;
export const SPR_H = 340;
export const BAR_Y = 700;

export const SeatFig: React.FC<{ seat: Seat; value: number; vmax: number; pose?: string; x?: number; opacity?: number;
  bob?: number }> = ({ seat, value, vmax, pose, x = ROW[seat], opacity = 1, bob = 0 }) => (
  <>
    <Shadow x={x} base={BASE} opacity={opacity} />
    <Sprite name={pose ?? `stand_${seat}`} x={x} base={BASE - bob} h={SPR_H} opacity={opacity} />
    <Bar x={x} y={BAR_Y} value={value} vmax={vmax} color={SEAT[seat]} opacity={opacity} />
  </>
);

/** The empty place of an agent that left: a dashed outline and a few short lines. */
export const Ghost: React.FC<{ x: number; lines: string[]; opacity: number; title?: string }> = ({ x, lines, opacity, title = "떠남" }) => (
  <div style={{ position: "absolute", left: x - 130, top: BASE - 300, width: 260, height: 300, opacity, borderRadius: 26,
    border: "2px dashed rgba(255,255,255,0.18)", display: "flex", flexDirection: "column", alignItems: "center",
    justifyContent: "center", gap: 10 }}>
    <div style={{ fontSize: 42, fontWeight: 800, color: C.dim }}>{title}</div>
    {lines.map((l) => <div key={l} style={{ fontSize: 26, fontWeight: 500, color: C.dim }}>{l}</div>)}
  </div>
);

// --- effects -------------------------------------------------------------------------------------------------------

export const Coin: React.FC<{ x: number; y: number; r?: number; opacity?: number }> = ({ x, y, r = 24, opacity = 1 }) => (
  <div style={{ position: "absolute", left: x - r, top: y - r, width: 2 * r, height: 2 * r, borderRadius: r, opacity,
    background: `radial-gradient(circle at 35% 30%, #fff1b8, ${C.gold} 45%, #b9861a)`,
    boxShadow: "0 0 24px rgba(243,194,79,0.55), inset 0 0 0 3px rgba(150,105,20,0.7)" }}>
    <div style={{ position: "absolute", inset: r * 0.42, borderRadius: "50%", border: "2px solid rgba(150,105,20,0.7)" }} />
  </div>
);

/** A coin flying on an arc from (x0, y0) to (x1, y1) between frames f0 and f0 + len. */
export const FlyingCoin: React.FC<{ f0: number; len: number; x0: number; y0: number; x1: number; y1: number; lift?: number }> =
  ({ f0, len, x0, y0, x1, y1, lift = 120 }) => {
    const frame = useCurrentFrame();
    if (frame < f0 || frame > f0 + len + 8) return null;
    const k = prog(frame, f0, len, (t) => t * t * (3 - 2 * t));
    const fade = 1 - prog(frame, f0 + len, 8);
    const appear = prog(frame, f0, 5);
    return (
      <>
        {[0.16, 0.08].map((d, i) => {  // a short trail
          const kk = Math.max(0, k - d);
          return <Coin key={i} x={x0 + (x1 - x0) * kk} y={y0 + (y1 - y0) * kk - lift * Math.sin(Math.PI * kk)} r={24 - 7 * (i + 1)}
            opacity={0.25 * appear * fade} />;
        })}
        <Coin x={x0 + (x1 - x0) * k} y={y0 + (y1 - y0) * k - lift * Math.sin(Math.PI * k)} opacity={appear * fade} />
      </>
    );
  };

/** A label that rises and fades over 1.6 s from f0. */
export const Floater: React.FC<{ f0: number; x: number; y: number; text: string; color: string; size?: number }> =
  ({ f0, x, y, text, color, size = 40 }) => {
    const frame = useCurrentFrame();
    if (frame < f0 || frame > f0 + 48) return null;
    const k = (frame - f0) / 48;
    const a = Math.min(1, k / 0.12) * (1 - Math.max(0, (k - 0.6) / 0.4));
    return (
      <div style={{ position: "absolute", left: x, top: y - 50 * easeOut(k), transform: "translate(-50%,-50%)", opacity: a,
        fontSize: size, fontWeight: 800, color, whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums",
        textShadow: "0 4px 18px rgba(0,0,0,0.6)" }}>{text}</div>
    );
  };

/** A rounded label that pops in with a spring from frame f0 (and fades out from `out`, if given). */
export const Badge: React.FC<{ f0: number; x: number; y: number; text: string; bg: string; ink?: string; size?: number;
  out?: number }> = ({ f0, x, y, text, bg, ink = "#fff", size = 30, out }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    if (frame < f0) return null;
    const s = spring({ frame: frame - f0, fps, config: { damping: 14, stiffness: 170, mass: 0.7 } });
    const o = out != null ? 1 - prog(frame, out, 8) : 1;
    return (
      <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) scale(${0.6 + 0.4 * s})`,
        opacity: Math.min(1, s * 1.4) * o, padding: `${size * 0.32}px ${size * 0.7}px`, borderRadius: size * 0.55,
        background: bg, color: ink, fontSize: size, fontWeight: 800, whiteSpace: "nowrap", letterSpacing: -0.3,
        boxShadow: `0 10px 30px -10px ${bg}` }}>
        <Rich text={text} size={size} />
      </div>
    );
  };

/** A check mark or a cross drawn stroke by stroke (k: 0..1). */
export const Mark: React.FC<{ kind: "check" | "cross"; x: number; y: number; s: number; k: number; color: string; width?: number }> =
  ({ kind, x, y, s, k, color, width = 8 }) => {
    const d = kind === "check" ? `M ${-s} 0 L ${-s * 0.3} ${s * 0.7} L ${s} ${-s * 0.8}` : `M ${-s} ${-s} L ${s} ${s} M ${s} ${-s} L ${-s} ${s}`;
    const len = kind === "check" ? s * 3.2 : s * 5.7;
    return (
      <svg style={{ position: "absolute", left: x - s - width, top: y - s - width, overflow: "visible" }} width={2 * s + 2 * width}
        height={2 * s + 2 * width}>
        <path d={d} transform={`translate(${s + width},${s + width})`} fill="none" stroke={color} strokeWidth={width}
          strokeLinecap="round" strokeLinejoin="round" strokeDasharray={len} strokeDashoffset={len * (1 - k)} />
      </svg>
    );
  };

/** The green EXIT sign (optionally struck through, k = the strike's progress). */
export const ExitSign: React.FC<{ x: number; y: number; scale?: number; strike?: number; opacity?: number }> =
  ({ x, y, scale = 1, strike = 0, opacity = 1 }) => (
    <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) scale(${scale})`, opacity }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 16px", borderRadius: 10, background: "#1f7a52",
        boxShadow: "0 0 24px rgba(56,201,127,0.35)", color: "#fff", fontSize: 30, fontWeight: 900, letterSpacing: 1 }}>
        EXIT <Arrow dir="→" size={28} color="#fff" />
      </div>
      {strike > 0 ? (
        <svg style={{ position: "absolute", left: -10, top: -10, overflow: "visible" }} width={10} height={10}>
          <line x1={0} y1={0} x2={0 + 158 * strike} y2={0 + 66 * strike} stroke={C.red} strokeWidth={7} strokeLinecap="round" />
        </svg>
      ) : null}
    </div>
  );
