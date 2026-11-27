// The trailer (docs/notes/2026-11-26-trailer-plan.md, and the order in timing.ts): 58.9 s, 24 fps, fifteen scenes cut
// hard against each other: the welcome, the rules, what a player may do, the question.
//   TrailerFilm      the film version: the scenes on generated live-action plates (./film.tsx); the one on the site
//   Trailer          the sprite version: the scenes drawn with the vector figures of ./figure.tsx (the two scenes
//                    the three scenes added on 2026-11-27, T17-T19, are plain cards there)
//   TrailerAnimatic  black cards with each scene's number and one line, to judge the rhythm and the sound alone
// All carry the same sound (the opening chant, synthesised effects of scripts/sfx.mjs, the host's lines), the letterbox
// with the captions in the lower bar, and the red words of T14.
import React from "react";
import { AbsoluteFill, Html5Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import { C, FONT, prog } from "../theme";
import { Loop, Sfx } from "../drama/kit";
import { BAR, CHANT, CHANT_BEATS, FPS, LINES, OFF, SCENES, T15_CUT, TOTAL, scene } from "./timing";
import { T01, T02, T03, T04, T05, T06, T07, T08, T09, T10, T11, T12, T13, T14, T15, T16 } from "./scenes";
import { F01, F02, F03, F06, F07, F09, F10, F12, F12_FAIL, F13, F13_OUT, F14, F15, F17, F18, F19, F19_OK } from "./film";

const VIEW: Record<string, React.FC> = { T01, T02, T03, T04, T05, T06, T07, T08, T09, T10, T11, T12, T13, T14, T15, T16 };
// which part of each generated clip is shown, and how fast (the clips are 4.2 s, the task's 6 s)
const FILM: Record<string, React.FC> = { T01: F01, T02: F02, T03: F03, T06: F06, T07: F07,
  T09: () => <F09 from={6} rate={1.9} />, T10: F10, T12: F12, T13: F13, T14: () => <F14 from={118} rate={0.4} />, T15: F15, T16, T17: F17, T18: F18, T19: F19 };
const S = (id: string) => scene(id).from;
const E = (id: string) => scene(id).from + scene(id).len;
/** A scene the sprite version has no drawing for: its name on black. */
const Card: React.FC<{ id: string }> = ({ id }) => (
  <AbsoluteFill style={{ background: "#000", alignItems: "center", justifyContent: "center", fontFamily: FONT, fontSize: 44, fontWeight: 600, color: C.faint }}>{scene(id).name}</AbsoluteFill>
);

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

/** Every sound on the video's clock. The chant in the dark; the entrance and a rising bed under the rules; a cut to
 * near silence while the gauge runs out (T12-T14: a clock, the wrong answers, one low hit under the red words); then
 * the bed again, low, under the choices. Everything but the voice gives way while the host speaks. `fails` are the
 * frames of T12's two wrong answers, `out13` the frame of T13 where the last cell goes out, `ok19` the frame of T19
 * where the team's answer is right. */
const Sound: React.FC<{ fails?: number[]; out13?: number; ok19?: number }> = ({ fails = [14, 35], out13 = 29, ok19 = 48 }) => {
  const rules = S("T03"), quiet = S("T12"), back = S("T18"), end = S("T15");
  const lines = Object.values(LINES);
  const duck = (f: number) => (lines.some((l) => f >= l.from - 4 && f < l.from + l.frames) ? 0.45 : 1);
  const steps = (from: number, n: number, every: number, v = 0.5) => Array.from({ length: n }, (_, i) => <Sfx key={`${from}-${i}`} at={from + i * every} name="step" volume={v} len={8} />);
  return (
    <>
      <Sfx at={CHANT} name="chant" volume={0.6} len={170} />
      {CHANT_BEATS.map((at, n) => <Sfx key={at} at={at} name={`bell${n + 1}`} volume={0.26} len={60} />)}
      <Sequence from={43} durationInFrames={quiet - 43} layout="none">
        <Html5Audio src={staticFile("sfx/drone.mp3")} loop volume={(f) => (f + 43 < rules ? 0.13 : 0.24) * duck(f + 43) * Math.min(1, f / 40, (quiet - 43 - f) / 2)} />
      </Sequence>
      <Sequence from={back} durationInFrames={end - back} layout="none">
        <Html5Audio src={staticFile("sfx/drone.mp3")} loop volume={(f) => 0.15 * duck(f + back) * Math.min(1, f / 14, (end - back - f) / 6)} />
      </Sequence>
      <Tick from={S("T02")} to={rules} />
      <Tick from={quiet} to={S("T14")} volume={0.16} />
      <Tick from={S("T15")} to={S("T16") - 6} />
      <Sfx at={rules} name="horn" volume={0.75} len={132} />
      {[0, 6, 12, 18].map((d) => <Sfx key={d} at={rules + d} name="clunk" volume={0.28} len={24} />)}
      <Sfx at={rules + Math.floor(scene("T03").len / 2)} name="clunk" volume={0.45} len={24} />
      <Sfx at={S("T17")} name="hit" volume={0.4} len={84} />
      <Pulse from={S("T17") + 20} to={quiet} rate={1.67} volume={0.3} />
      {fails.map((d) => <Sfx key={d} at={quiet + d} name="hit" volume={0.2} len={30} />)}
      <Sfx at={S("T13") + out13} name="power" volume={0.22} len={48} />
      <Sfx at={OFF.at} name="hit" volume={0.42} len={84} />
      <Pulse from={S("T09")} to={E("T19")} rate={0.83} volume={0.3} />
      <Sfx at={S("T09") + 9} name="whoosh" volume={0.07} len={40} />
      <Sfx at={S("T10") + 53 + 14} name="chime" volume={0.5} len={38} />
      {[10, 20, 30, 40].map((d) => <Sfx key={d} at={S("T19") + d} name="tick" volume={0.3} len={5} />)}
      <Sfx at={S("T19") + ok19} name="chime" volume={0.5} len={38} />
      {steps(S("T06") + 5, 7, 13, 0.4)}
      <Sfx at={S("T07")} name="thud" volume={0.6} len={34} />
      {[0, 5, 10].map((d) => <Sfx key={d} at={S("T15") + d} name="clunk" volume={d === 10 ? 0.5 : 0.25} len={24} />)}
      <Sfx at={S("T16") + 12} name="hit" volume={0.6} len={84} />
      {lines.map((l) => (
        <Sequence key={l.src} from={l.from} durationInFrames={l.frames + 3} layout="none"><Html5Audio src={staticFile(l.src)} /></Sequence>
      ))}
    </>
  );
};

/** The letterbox, the line spoken now in the lower bar (Korean over English), and in T14 the red words over the
 * picture. */
const Over: React.FC = () => {
  const f = useCurrentFrame();
  const line = Object.values(LINES).find((l) => f >= l.from - 2 && f < l.from + l.frames + 6);
  const la = line ? prog(f, line.from - 2, 4) * (1 - prog(f, line.from + line.frames, 6)) : 0;
  const off = f >= OFF.at && f < OFF.at + OFF.len;
  const oa = off ? prog(f, OFF.at, 3) * (1 - prog(f, OFF.at + OFF.len - 6, 6)) : 0;
  const bars = f < scene("T16").from;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.ink }}>
      {bars ? <><div style={{ position: "absolute", left: 0, right: 0, top: 0, height: BAR, background: "#000" }} />
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: BAR, background: "#000" }} /></> : null}
      {off ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: BAR, bottom: BAR, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          opacity: oa, transform: `scale(${1.06 - 0.06 * prog(f, OFF.at, 10)})` }}>
          <div style={{ fontSize: 168, fontWeight: 900, letterSpacing: -3, color: "#ff2f40", textShadow: "0 0 34px rgba(255,47,64,0.75), 0 0 110px rgba(255,47,64,0.45), 0 4px 14px rgba(0,0,0,0.9)" }}>{OFF.ko}</div>
          <div style={{ marginTop: 2, fontSize: 34, fontWeight: 500, color: "rgba(255,150,158,0.9)", textShadow: "0 2px 10px rgba(0,0,0,0.95)" }}>{OFF.en}</div>
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
    {SCENES.map((s) => { const View = VIEW[s.id]; return <Sequence key={s.id} from={s.from} durationInFrames={s.len}>{View ? <View /> : <Card id={s.id} />}</Sequence>; })}
    <Over />
    <Sound />
  </AbsoluteFill>
);

export const TrailerFilm: React.FC = () => (
  <AbsoluteFill style={{ background: "#000" }}>
    {SCENES.map((s) => { const View = FILM[s.id]; return <Sequence key={s.id} from={s.from} durationInFrames={s.len}><View /></Sequence>; })}
    <Over />
    <Sound fails={F12_FAIL} out13={F13_OUT} ok19={F19_OK} />
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
