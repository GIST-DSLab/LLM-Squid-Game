// The trailer (docs/notes/2026-11-26-trailer-plan.md): 45 s, 24 fps, sixteen scenes cut hard against each other.
//   Trailer          the sprite version: every scene drawn with the vector figures of ./figure.tsx
//   TrailerFilm      the film version: the same scenes on generated live-action plates (./film.tsx)
//   TrailerAnimatic  black cards with each scene's number and one line, to judge the rhythm and the sound alone
// Both carry the same sound (synthesised effects of scripts/sfx.mjs and the host's three lines), the letterbox with the
// captions in the lower bar, and the three chunk titles of act 2.
import React from "react";
import { AbsoluteFill, Html5Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import { C, FONT, prog } from "../theme";
import { Loop, Sfx } from "../drama/kit";
import { BAR, CHUNKS, FPS, LINES, SCENES, T15_CUT, TOTAL, scene } from "./timing";
import { T01, T02, T03, T04, T05, T06, T07, T08, T09, T10, T11, T12, T13, T14, T15, T16 } from "./scenes";
import { F01, F02, F03, F04, F05, F06, F07, F08, F08_CUT, F09, F10, F11, F12, F13, F14, F15 } from "./film";

const VIEW: Record<string, React.FC> = { T01, T02, T03, T04, T05, T06, T07, T08, T09, T10, T11, T12, T13, T14, T15, T16 };
// which part of each generated clip is shown, and how fast (the clips are 4.2 s; the cuts are shorter)
const FILM: Record<string, React.FC> = { T01: F01, T02: F02, T03: F03, T04: F04, T05: F05, T06: () => <F06 runFrom={30} runRate={1.5} />, T07: F07, T08: F08,
  T09: () => <F09 from={6} rate={1.9} />, T10: F10, T11: F11, T12: F12, T13: F13, T14: F14, T15: F15, T16 };
const S = (id: string) => scene(id).from;

/** A loop of the clock's tick (the file holds a tick and a tock, one a second) at `rate` times its speed. */
const Tick: React.FC<{ from: number; to: number; rate?: number; volume?: number }> = ({ from, to, rate = 1, volume = 0.2 }) => (
  <Sequence from={from} durationInFrames={to - from} layout="none">
    <Html5Audio src={staticFile("sfx/tick.mp3")} loop playbackRate={rate} volume={(f) => volume * Math.min(1, f / 3, (to - from - f) / 2)} />
  </Sequence>
);
const Pulse: React.FC<{ from: number; to: number; rate: number; volume: number }> = ({ from, to, rate, volume }) => (
  <Sequence from={from} durationInFrames={to - from} layout="none">
    <Html5Audio src={staticFile("sfx/pulse.mp3")} loop playbackRate={rate} volume={(f) => volume * Math.min(1, f / 6, (to - from - f) / 2)} />
  </Sequence>
);

/** Every sound on the video's clock. Loud, then quiet, then nothing: T13 and T14 are silent. */
const Sound: React.FC<{ door8?: number }> = ({ door8 = 32 }) => {
  const hush = S("T13");
  const duck = (f: number) => (f >= LINES.welcome.from - 4 && f < LINES.welcome.from + LINES.welcome.frames ? 0.5 : 1);
  const steps = (from: number, n: number, every: number) => Array.from({ length: n }, (_, i) => <Sfx key={`${from}-${i}`} at={from + i * every} name="step" volume={0.5} len={8} />);
  return (
    <>
      <Sequence from={43} durationInFrames={hush - 43} layout="none">
        <Html5Audio src={staticFile("sfx/drone.mp3")} loop volume={(f) => 0.15 * duck(f + 43) * Math.min(1, f / 40, (hush - 43 - f) / 2)} />
      </Sequence>
      <Tick from={0} to={S("T04")} />
      <Tick from={S("T04")} to={S("T06")} rate={2} />
      <Tick from={S("T12")} to={hush} />
      <Tick from={S("T15")} to={S("T16") - 6} />
      <Pulse from={S("T09")} to={S("T12")} rate={0.83} volume={0.3} />
      <Pulse from={S("T12") + 42} to={hush} rate={1.67} volume={0.34} />
      {[[19, 0.25], [31, 0.25], [43, 0.5]].map(([at, v]) => <Sfx key={at} at={at} name="clunk" volume={v} len={24} />)}
      {[0, 6, 12, 18].map((d) => <Sfx key={d} at={S("T03") + d} name="clunk" volume={0.32} len={24} />)}
      <Sfx at={S("T03") + 30} name="clunk" volume={0.55} len={24} />
      <Sfx at={S("T05") + 12} name="pulse" volume={0.4} len={24} />
      <Sfx at={S("T06")} name="whoosh" volume={0.3} len={58} />
      {steps(S("T06") + 2, 12, 5)}
      <Sfx at={S("T07")} name="thud" volume={0.6} len={34} />
      {steps(S("T08") + 4, 6, 4)}
      <Sfx at={S("T08") + door8} name="thud" volume={0.6} len={34} />
      <Sfx at={S("T09") + 9} name="whoosh" volume={0.07} len={40} />
      <Sfx at={S("T10") + 53 + 14} name="chime" volume={0.5} len={38} />
      {[6, 13].map((d) => <Sfx key={d} at={S("T11") + d} name="tick" volume={0.3} len={5} />)}
      {[14, 35].map((d) => <Sfx key={d} at={S("T12") + d} name="hit" volume={0.32} len={30} />)}
      <Sfx at={S("T13") + 29} name="thud" volume={0.12} len={30} />
      {[0, 5, 10].map((d) => <Sfx key={d} at={S("T15") + d} name="clunk" volume={d === 10 ? 0.5 : 0.25} len={24} />)}
      <Sfx at={S("T16") + 12} name="hit" volume={0.6} len={84} />
      {Object.values(LINES).map((l) => (
        <Sequence key={l.src} from={l.from} durationInFrames={l.frames + 3} layout="none"><Html5Audio src={staticFile(l.src)} /></Sequence>
      ))}
    </>
  );
};

const SHAPE: Record<string, React.ReactNode> = {
  circle: <circle cx={20} cy={20} r={15} />,
  triangle: <path d="M 20 4 L 37 34 L 3 34 Z" strokeLinejoin="round" />,
  square: <rect x={5} y={5} width={30} height={30} />,
};

/** The letterbox, the line spoken now in the lower bar (Korean over English), and a chunk's shape and three letters
 * at the top left for its first 1.2 s (top right in the film version, whose door and EXIT sign are at the left). */
const Over: React.FC<{ right?: boolean }> = ({ right }) => {
  const f = useCurrentFrame();
  const line = Object.values(LINES).find((l) => f >= l.from - 2 && f < l.from + l.frames + 6);
  const la = line ? prog(f, line.from - 2, 4) * (1 - prog(f, line.from + line.frames, 6)) : 0;
  const chunk = CHUNKS.find((c) => f >= c.at && f < c.at + 29);
  const ca = chunk ? prog(f, chunk.at, 4) * (1 - prog(f, chunk.at + 23, 6)) : 0;
  const bars = f < scene("T16").from;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.ink }}>
      {bars ? <><div style={{ position: "absolute", left: 0, right: 0, top: 0, height: BAR, background: "#000" }} />
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: BAR, background: "#000" }} /></> : null}
      {chunk ? (
        <div style={{ position: "absolute", ...(right ? { right: 96 } : { left: 96 }), top: BAR + 40, opacity: ca, textShadow: "0 2px 10px rgba(0,0,0,0.9)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 34, fontWeight: 700 }}>
            <svg width={40} height={40} viewBox="0 0 40 40" fill="none" stroke={C.pink} strokeWidth={3.5}>{SHAPE[chunk.shape]}</svg>{chunk.ko}
          </div>
          <div style={{ marginLeft: 56, marginTop: 4, fontSize: 22, fontWeight: 500, color: C.dim }}>{chunk.en}</div>
        </div>
      ) : null}
      {line ? (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: BAR, display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", opacity: la }}>
          <div style={{ fontSize: 38, fontWeight: 500, letterSpacing: -0.2, color: "#f1f1f4" }}>{line.text}</div>
          <div style={{ marginTop: 6, fontSize: 24, fontWeight: 400, color: C.dim }}>{line.en}</div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const Trailer: React.FC = () => (
  <AbsoluteFill style={{ background: "#000" }}>
    {SCENES.map((s) => { const View = VIEW[s.id]; return <Sequence key={s.id} from={s.from} durationInFrames={s.len}><View /></Sequence>; })}
    <Over />
    <Sound />
  </AbsoluteFill>
);

export const TrailerFilm: React.FC = () => (
  <AbsoluteFill style={{ background: "#000" }}>
    {SCENES.map((s) => { const View = FILM[s.id]; return <Sequence key={s.id} from={s.from} durationInFrames={s.len}><View /></Sequence>; })}
    <Over right />
    <Sound door8={F08_CUT} />
  </AbsoluteFill>
);

const stamp = (frame: number) => `0:${(frame / FPS).toFixed(1).padStart(4, "0")}`;

export const TrailerAnimatic: React.FC = () => {
  const f = useCurrentFrame();
  const s = SCENES.find((x) => f >= x.from && f < x.from + x.len) ?? SCENES[SCENES.length - 1];
  const cut = s.id === "T15" && f - s.from >= T15_CUT ? " (가면 근접)" : "";
  return (
    <AbsoluteFill style={{ background: "#000", fontFamily: FONT, color: C.ink }}>
      <div style={{ position: "absolute", left: 160, top: 300, fontSize: 30, fontWeight: 600, letterSpacing: 3, color: C.pink }}>{s.part}</div>
      <div style={{ position: "absolute", left: 160, top: 350, fontSize: 132, fontWeight: 900, letterSpacing: -2 }}>{s.id}
        <span style={{ marginLeft: 36, fontSize: 60, fontWeight: 700, letterSpacing: -1 }}>{s.name}{cut}</span></div>
      <div style={{ position: "absolute", left: 160, top: 540, width: 1500, fontSize: 40, fontWeight: 500, color: C.dim, wordBreak: "keep-all" }}>{s.note}</div>
      <div style={{ position: "absolute", left: 160, top: 640, fontSize: 30, fontWeight: 500, color: C.faint, fontVariantNumeric: "tabular-nums" }}>
        {stamp(s.from)} – {stamp(s.from + s.len)} · {(s.len / FPS).toFixed(1)}초</div>
      <div style={{ position: "absolute", left: 160, right: 160, top: 760, height: 14, display: "flex", gap: 4 }}>
        {SCENES.map((x) => <div key={x.id} style={{ flex: x.len, background: x.id === s.id ? C.pink : f >= x.from ? "rgba(255,255,255,0.4)" : "rgba(255,255,255,0.12)" }} />)}
      </div>
      <div style={{ position: "absolute", left: 160 + (1600 * f) / TOTAL, top: 752, width: 2, height: 30, background: "#fff" }} />
      <Over />
      <Sound />
    </AbsoluteFill>
  );
};
