// Building blocks of the drama version (ArenaRulesDrama): a dark stage with a slow push-in, spotlights that light the
// seats (a sprite is dark unless a light is on it), the letterbox with film-like captions in the lower bar, title
// cards, the host (the supervisor as a backlit silhouette only — no colour, no face, its sign cropped off), counters,
// and sound effects placed on a scene's frames. Coordinates are on the 1920x1080 frame; the picture is between the bars.
import React from "react";
import { AbsoluteFill, Html5Audio, Img, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, SEAT, Seat, easeOut, prog } from "../theme";
import { useBeats } from "../ui";

export const BAR = 118;           // letterbox bar height (picture: 118..962)
export const FLOOR = 770;         // the seats' floor line
export const X: Record<Seat, number> = { blue: 300, orange: 660, green: 1020, purple: 1380 };
export const DOOR_X = 1745;
export const H = 330;             // sprite height on the floor
export const n = (v: number) => (Math.round(v / 10) * 10).toLocaleString("en-US");
export const lit = (k: number) => `brightness(${0.13 + 0.87 * k}) saturate(${0.35 + 0.65 * k})`;

/** A light switching on at f0 with two short flickers (0..1). */
export function flick(frame: number, f0: number, len = 10): number {
  if (frame < f0) return 0;
  const d = frame - f0;
  if (d < 2) return 0.7;
  if (d < 4) return 0.1;
  if (d < 5) return 0.5;
  if (d < 7) return 0.15;
  return prog(frame, f0 + 7, len);
}

// --- frame ---------------------------------------------------------------------------------------------------------

/** The dark stage; children are pushed in slowly toward (ox, oy) over the scene; `over` (the letterbox, title cards)
 * stays still on top. */
export const DramaStage: React.FC<{ children?: React.ReactNode; over?: React.ReactNode; push?: number; ox?: number; oy?: number; tint?: string }> =
  ({ children, over, push = 0.06, ox = 960, oy = 560, tint = "rgba(70,80,120,0.10)" }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();
    const s = 1 + push * prog(frame, 0, durationInFrames, (t) => t);
    return (
      <AbsoluteFill style={{ background: "#050507", fontFamily: FONT, color: C.ink, overflow: "hidden" }}>
        <AbsoluteFill style={{ transform: `scale(${s})`, transformOrigin: `${ox}px ${oy}px` }}>
          <AbsoluteFill style={{ background: `radial-gradient(1100px 560px at 50% 30%, ${tint}, transparent 70%)` }} />
          <div style={{ position: "absolute", left: -200, right: -200, top: FLOOR - 6, height: 420,
            background: "linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0) 60%)" }} />
          {children}
        </AbsoluteFill>
        <AbsoluteFill style={{ background: "radial-gradient(1300px 760px at 50% 52%, transparent 50%, rgba(0,0,0,0.75) 100%)" }} />
        {over}
      </AbsoluteFill>
    );
  };

/** A cone of light from above onto (x, FLOOR) and its pool on the floor; k = brightness 0..1. */
export const Spot: React.FC<{ x: number; k: number; w?: number; color?: string; top?: number }> =
  ({ x, k, w = 170, color = "255,236,200", top = BAR }) => k <= 0.001 ? null : (
    <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, mixBlendMode: "screen", pointerEvents: "none" }}>
      <defs>
        <linearGradient id={`cone${x}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={`rgb(${color})`} stopOpacity={0.22 * k} />
          <stop offset="1" stopColor={`rgb(${color})`} stopOpacity={0.10 * k} />
        </linearGradient>
        <radialGradient id={`pool${x}`}>
          <stop offset="0" stopColor={`rgb(${color})`} stopOpacity={0.42 * k} />
          <stop offset="1" stopColor={`rgb(${color})`} stopOpacity={0} />
        </radialGradient>
      </defs>
      <polygon points={`${x - 22},${top} ${x + 22},${top} ${x + w},${FLOOR + 10} ${x - w},${FLOOR + 10}`} fill={`url(#cone${x})`} />
      <ellipse cx={x} cy={FLOOR + 4} rx={w * 1.15} ry={30} fill={`url(#pool${x})`} />
    </svg>
  );

/** A tracksuit sprite standing on the floor at x, lit by k (dark at 0). */
export const Agent: React.FC<{ name: string; x: number; k: number; h?: number; base?: number; opacity?: number; bob?: number }> =
  ({ name, x, k, h = H, base = FLOOR, opacity = 1, bob = 0 }) => (
    <>
      <div style={{ position: "absolute", left: x - 110, top: base - 12, width: 220, height: 24, borderRadius: "50%", opacity: opacity * (0.3 + 0.7 * k),
        background: "radial-gradient(closest-side, rgba(0,0,0,0.7), transparent)" }} />
      <Img src={staticFile(`sprites/${name}.png`)} style={{ position: "absolute", left: x, top: base - h - bob, height: h,
        transform: "translateX(-50%)", filter: lit(k), opacity }} />
    </>
  );

/** A seat's balance under it: the number in tabular figures over a thin line in the seat's colour. */
export const Counter: React.FC<{ x: number; value: number; seat: Seat; k?: number; y?: number; red?: boolean; size?: number; max?: number }> =
  ({ x, value, seat, k = 1, y = FLOOR + 30, red, size = 44, max = 40_000 }) => {
    const zero = Math.round(value / 10) <= 0;
    return (
      <div style={{ position: "absolute", left: x - 130, top: y, width: 260, textAlign: "center", opacity: 0.25 + 0.75 * k }}>
        <div style={{ fontSize: size, fontWeight: 700, letterSpacing: -0.5, fontVariantNumeric: "tabular-nums",
          color: zero || red ? C.red : C.ink, textShadow: zero || red ? "0 0 22px rgba(239,79,90,0.55)" : "none" }}>{n(value)}</div>
        <div style={{ margin: "8px auto 0", width: 180, height: 3, background: "rgba(255,255,255,0.08)" }}>
          <div style={{ height: "100%", width: `${Math.max(0, Math.min(1, value / max)) * 100}%`, background: SEAT[seat] }} />
        </div>
      </div>
    );
  };

/** The host: the supervisor sprite as a black, rim-lit silhouette with its sign cropped off, on a high platform. */
export const Host: React.FC<{ x: number; base: number; h: number; k: number; flip?: boolean }> = ({ x, base, h, k, flip }) => {
  if (k <= 0.001) return null;
  const crop = 0.185, w = h * (445 / 760);
  return (
    <div style={{ position: "absolute", left: x - w / 2, top: base - h * (1 - crop), width: w, height: h * (1 - crop), opacity: k }}>
      <div style={{ position: "absolute", left: -w * 0.6, top: -h * 0.25, width: w * 2.2, height: h * 1.2,
        background: "radial-gradient(closest-side, rgba(150,165,215,0.28), transparent)" }} />
      <div style={{ position: "absolute", inset: 0, overflow: "hidden", transform: flip ? "scaleX(-1)" : undefined }}>
        <Img src={staticFile("sprites/guard_sign.png")} style={{ position: "absolute", left: 0, top: -h * crop, height: h,
          filter: "brightness(0) drop-shadow(0 0 1.5px rgba(205,215,255,0.75)) drop-shadow(0 0 10px rgba(150,165,215,0.35))" }} />
      </div>
      <div style={{ position: "absolute", left: -w * 0.35, right: -w * 0.35, top: h * (1 - crop) - 4, height: 8, borderRadius: 3, background: "#15151c",
        boxShadow: "0 0 0 1px rgba(255,255,255,0.05)" }} />
    </div>
  );
};

// --- the letterbox and captions --------------------------------------------------------------------------------------

/** The bars (sliding in during the first frames of the video when `open`) and the line spoken now, in the lower bar. */
export const Letterbox: React.FC<{ open?: boolean; label?: string; note?: string }> = ({ open, label, note }) => {
  const frame = useCurrentFrame();
  const { beats } = useBeats();
  const h = open ? BAR * prog(frame, 0, 24) : BAR;
  let cap: React.ReactNode = null;
  for (const b of beats) {
    const end = b.start + Math.round(b.audioSeconds * 30) + 10;
    if (frame >= b.start - 3 && frame < end + 6) {
      const a = prog(frame, b.start - 3, 6) * (1 - prog(frame, end, 6));
      cap = <div style={{ opacity: a }}>{b.text}</div>;
    }
  }
  const la = prog(frame, 8, 16);
  return (
    <>
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: h, background: "#000", zIndex: 40 }} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: h, background: "#000", zIndex: 40 }} />
      {label ? <div style={{ position: "absolute", left: 72, top: 44, zIndex: 41, fontSize: 22, fontWeight: 600, letterSpacing: 3,
        color: "rgba(255,255,255,0.42)", opacity: la }}>{label}</div> : null}
      {note ? <div style={{ position: "absolute", right: 72, top: 46, zIndex: 41, fontSize: 20, fontWeight: 500, letterSpacing: 0.5,
        color: "rgba(255,255,255,0.32)", opacity: la }}>{note}</div> : null}
      <div style={{ position: "absolute", left: 120, right: 120, bottom: 0, height: BAR, zIndex: 41, display: "flex", alignItems: "center",
        justifyContent: "center", textAlign: "center", fontSize: 38, fontWeight: 500, lineHeight: 1.3, letterSpacing: -0.2,
        wordBreak: "keep-all", color: "#f1f1f4", textShadow: "0 2px 6px rgba(0,0,0,0.9)" }}>{cap}</div>
    </>
  );
};

/** A centred title card over a darkened picture: a small overline, the title, a thin pink rule that draws out. */
export const TitleCard: React.FC<{ f0: number; len: number; over?: string; title: string; sub?: string; size?: number }> =
  ({ f0, len, over, title, sub, size = 118 }) => {
    const frame = useCurrentFrame();
    if (frame < f0 || frame > f0 + len) return null;
    const a = prog(frame, f0, 18) * (1 - prog(frame, f0 + len - 14, 14));
    const t = prog(frame, f0 + 4, 30);
    const rule = prog(frame, f0 + 14, 30);
    return (
      <AbsoluteFill style={{ zIndex: 30, background: `rgba(0,0,0,${0.72 * a})`, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", opacity: a }}>
        {over ? <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: 12, color: C.pinkSoft, marginBottom: 26, opacity: t }}>{over}</div> : null}
        <div style={{ fontSize: size, fontWeight: 900, letterSpacing: 6 + 10 * (1 - t), color: "#f6f6f9", lineHeight: 1,
          textShadow: "0 0 50px rgba(232,51,109,0.25)", transform: `scale(${1.04 - 0.04 * t})` }}>{title}</div>
        <div style={{ marginTop: 34, width: 420 * rule, height: 3, background: C.pink, boxShadow: `0 0 18px ${C.pink}` }} />
        {sub ? <div style={{ marginTop: 26, fontSize: 32, fontWeight: 500, letterSpacing: 4, color: "rgba(255,255,255,0.65)", opacity: rule }}>{sub}</div> : null}
      </AbsoluteFill>
    );
  };

/** A short line of text placed in the picture, fading in at f0 (and out at `out`). */
export const Note: React.FC<{ f0: number; out?: number; x: number; y: number; w?: number; size?: number; color?: string;
  weight?: number; align?: "center" | "left"; children: React.ReactNode; style?: React.CSSProperties }> =
  ({ f0, out, x, y, w = 600, size = 28, color = C.ink, weight = 600, align = "center", children, style }) => {
    const frame = useCurrentFrame();
    const a = prog(frame, f0, 12) * (out != null ? 1 - prog(frame, out, 10) : 1);
    if (a <= 0) return null;
    return (
      <div style={{ position: "absolute", left: align === "center" ? x - w / 2 : x, top: y, width: w, textAlign: align, fontSize: size,
        fontWeight: weight, color, opacity: a, transform: `translateY(${(1 - a) * 10}px)`, wordBreak: "keep-all", ...style }}>{children}</div>
    );
  };

/** A label that rises and fades over 1.6 s from f0. */
export const Rise: React.FC<{ f0: number; x: number; y: number; text: string; color: string; size?: number }> =
  ({ f0, x, y, text, color, size = 40 }) => {
    const frame = useCurrentFrame();
    if (frame < f0 || frame > f0 + 48) return null;
    const k = (frame - f0) / 48;
    const a = Math.min(1, k / 0.12) * (1 - Math.max(0, (k - 0.6) / 0.4));
    return <div style={{ position: "absolute", left: x, top: y - 50 * easeOut(k), transform: "translate(-50%,-50%)", opacity: a, fontSize: size,
      fontWeight: 800, color, whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums", textShadow: "0 4px 18px rgba(0,0,0,0.7)" }}>{text}</div>;
  };

/** The EXIT door at DOOR_X: frame, warm light beyond, the leaf (open 0..1), the green sign (sign 0..1 lit, struck 0..1). */
export const Door: React.FC<{ open: number; sign: number; k: number; struck?: number }> = ({ open, sign, k, struck = 0 }) => {
  const w = 180, h = 340, top = FLOOR - h;
  return (
    <div style={{ filter: lit(Math.max(k, open)) }}>
      <div style={{ position: "absolute", left: DOOR_X - w / 2 - 14, top: top - 14, width: w + 28, height: h + 14, borderRadius: "10px 10px 0 0",
        background: "#24242d" }} />
      <div style={{ position: "absolute", left: DOOR_X - w / 2, top, width: w, height: h, background: "linear-gradient(180deg, #fff3d6, #ffcf86)",
        boxShadow: `0 0 ${90 * open}px ${30 * open}px rgba(255,205,130,0.35)` }} />
      <div style={{ position: "absolute", left: DOOR_X - w / 2, top, width: w, height: h, perspective: 900 }}>
        <div style={{ width: "100%", height: "100%", transformOrigin: "100% 50%", transform: `rotateY(${-80 * open}deg)`,
          background: "linear-gradient(90deg, #4a4a57, #3b3b46)", boxShadow: "inset 0 0 0 3px rgba(0,0,0,0.3)" }}>
          <div style={{ position: "absolute", left: 22, top: h / 2 - 7, width: 14, height: 14, borderRadius: 7, background: "#b9b9c4" }} />
        </div>
      </div>
      <div style={{ position: "absolute", left: DOOR_X, top: top - 58, transform: "translate(-50%,-50%)" }}>
        <div style={{ padding: "6px 18px", borderRadius: 8, fontSize: 30, fontWeight: 900, letterSpacing: 2, color: sign > 0.5 ? "#eafff3" : "#5b6b62",
          background: sign > 0.05 ? `rgba(31,122,82,${0.35 + 0.65 * sign})` : "#1a2620",
          boxShadow: `0 0 ${40 * sign}px rgba(56,201,127,${0.55 * sign})` }}>EXIT</div>
        {struck > 0 ? (
          <svg style={{ position: "absolute", left: -8, top: -6, overflow: "visible" }} width={10} height={10}>
            <line x1={0} y1={0} x2={128 * struck} y2={56 * struck} stroke={C.red} strokeWidth={6} strokeLinecap="round" />
          </svg>
        ) : null}
      </div>
    </div>
  );
};

// --- sound ---------------------------------------------------------------------------------------------------------

/** A one-shot effect (public/sfx/<name>.mp3) at frame f (scene-relative). */
export const Sfx: React.FC<{ at: number; name: string; volume?: number; len?: number }> = ({ at, name, volume = 0.5, len = 120 }) => (
  <Sequence from={Math.max(0, Math.round(at))} durationInFrames={len} layout="none">
    <Html5Audio src={staticFile(`sfx/${name}.mp3`)} volume={volume} />
  </Sequence>
);

/** A looped effect from frame `from` for `len` frames, faded in and out. */
export const Loop: React.FC<{ from: number; len: number; name: string; volume: number; fade?: number }> =
  ({ from, len, name, volume, fade = 12 }) => len <= 0 ? null : (
    <Sequence from={Math.max(0, Math.round(from))} durationInFrames={Math.round(len)} layout="none">
      <Html5Audio src={staticFile(`sfx/${name}.mp3`)} loop
        volume={(f) => volume * Math.min(1, f / fade, (len - f) / fade)} />
    </Sequence>
  );
