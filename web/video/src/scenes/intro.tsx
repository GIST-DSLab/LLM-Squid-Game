// Title, tokens = life, ① the solver pick.
import React from "react";
import { AbsoluteFill, Freeze, OffthreadVideo, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, SEAT, SEATS, T, lerp, prog } from "../theme";
import { BASE, Bar, Badge, Caption, EXAMPLE_NOTE, Floor, Heading, Insert, ROW, SPR_H, SeatFig, Shadow, Sprite, Stage, useBeats } from "../ui";

export const START = { blue: 40_000, orange: 20_000, green: 4_000, purple: 8_000 };
export const VMAX = 40_000;

/** A cinematic insert (public/inserts/*.mp4), muted, full frame; holds its last frame if the slot is longer. */
export const InsertClip: React.FC<{ insert: NonNullable<Insert>; len: number }> = ({ insert, len }) => {
  const frame = useCurrentFrame();
  const own = Math.max(1, Math.floor(insert.seconds * 30) - 1);
  const o = prog(frame, 0, 8) * (1 - prog(frame, len - 8, 8));
  const clip = <OffthreadVideo src={staticFile(insert.src)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />;
  return (
    <AbsoluteFill style={{ opacity: o, background: "#000" }}>
      <Sequence durationInFrames={Math.min(own, len)}>{clip}</Sequence>
      {len > own ? <Sequence from={own}><Freeze frame={own - 1}>{clip}</Freeze></Sequence> : null}
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.35), transparent 30%, transparent 60%, rgba(0,0,0,0.55))" }} />
    </AbsoluteFill>
  );
};

/** The three outline shapes of the title (circle, triangle, square), drawn stroke by stroke. */
const Marks: React.FC<{ k: number }> = ({ k }) => {
  const s = { fill: "none", stroke: C.pink, strokeWidth: 5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg width={330} height={90} viewBox="0 0 330 90" style={{ position: "absolute", left: 960 - 165, top: 120 }}>
      <circle cx={45} cy={45} r={36} {...s} strokeDasharray={227} strokeDashoffset={227 * (1 - k)} />
      <path d="M 165 9 L 204 79 L 126 79 Z" {...s} strokeDasharray={240} strokeDashoffset={240 * (1 - k)} />
      <rect x={250} y={9} width={70} height={70} rx={3} {...s} strokeDasharray={280} strokeDashoffset={280 * (1 - k)} />
    </svg>
  );
};

export const TitleScene: React.FC<{ insert: Insert; duration: number }> = ({ insert, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = prog(frame, 6, 22);
  return (
    <Stage glow="rgba(232,51,109,0.20)">
      {insert ? <InsertClip insert={insert} len={duration} /> : (
        <>
          <Floor y={880} />
          {SEATS.map((c, i) => {
            const s = spring({ frame: frame - 14 - 6 * i, fps, config: { damping: 15, stiffness: 120 } });
            const x = 960 + (i - 1.5) * 270;
            const bob = Math.sin((frame - 6 * i) / 11) * 4 * Math.min(1, frame / 50);
            return (
              <React.Fragment key={c}>
                <Shadow x={x} base={880} w={230} opacity={s} />
                <Sprite name={`stand_${c}`} x={x} base={880 + (1 - s) * 420 - Math.max(0, bob)} h={420} />
              </React.Fragment>
            );
          })}
        </>
      )}
      <Marks k={prog(frame, 0, 34)} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 236, textAlign: "center", opacity: a,
        transform: `translateY(${(1 - a) * 24}px)` }}>
        <div style={{ fontSize: T.display, fontWeight: 900, letterSpacing: -4, color: C.pink, lineHeight: 1,
          textShadow: "0 10px 50px rgba(232,51,109,0.35)" }}>LLM 오징어 게임</div>
        <div style={{ marginTop: 26, fontSize: 50, fontWeight: 600, color: C.ink, letterSpacing: -1 }}>한 라운드의 규칙</div>
      </div>
      <Caption />
    </Stage>
  );
};

export const TokensScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const starts = [60_000, 40_000, 20_000, 10_000];
  const drain = prog(frame, B(1, 0.4), 80) * 11_000;
  const a = prog(frame, 4, 18);
  return (
    <Stage>
      <div style={{ position: "absolute", left: 0, right: 0, top: 80, textAlign: "center", opacity: a,
        transform: `translateY(${(1 - a) * -16}px)`, fontSize: T.h1, fontWeight: 900, letterSpacing: -2 }}>
        토큰 <span style={{ color: C.pink }}>=</span> 목숨
      </div>
      <Floor y={640} />
      {SEATS.map((c, i) => {
        const x = 960 + (i - 1.5) * 360;
        const up = prog(frame, B(0, 0.2) + 5 * i, 34);
        const left = Math.max(0, starts[i] * up - drain);
        const off = drain > 0 && left <= 0;
        const low = left / starts[i] < 0.25;
        const shake = off ? Math.sin(frame * 2.2) * 6 * (1 - prog(frame, B(1, 0.4) + 74, 14)) : 0;
        return (
          <React.Fragment key={c}>
            <Shadow x={x} base={640} w={220} />
            <Sprite name={off ? "off" : `stand_${c}`} x={x + shake} base={640} h={360} />
            <Bar x={x} y={668} value={left} vmax={60_000} color={low && drain > 0 ? C.red : SEAT[c]} w={270} numSize={46} />
            {off ? <Badge f0={B(1, 0.4) + 72} x={x} y={236} text="꺼짐" bg={C.red} size={30} /> : null}
          </React.Fragment>
        );
      })}
      <Caption />
    </Stage>
  );
};

/** The supervisor on a platform at the right aims along the row and stops on the solver; a spotlight falls on it. */
export const PickScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const lock = B(0, 2.5);
  const on = prog(frame, lock, 14);
  const gx = 1730, gbase = 470, gh = 300, gw = gh * 0.717;
  const mx = gx - gw / 2 + 4, my = gbase - gh + 0.694 * gh;
  const sweep = [ROW.purple, ROW.green, ROW.blue, ROW.orange];
  const k = prog(frame, B(0, 0.3), lock - B(0, 0.3), (t) => t) * (sweep.length - 1);
  const i = Math.min(Math.floor(k), sweep.length - 2);
  const tx = lerp(sweep[i], sweep[i + 1], prog(k - i, 0, 1, (t) => t * t * (3 - 2 * t)));
  const ty = BASE - SPR_H * 0.56;
  const aimIn = prog(frame, B(0, 0.1), 10);
  const order = prog(frame, B(1, 0.1), 14);
  return (
    <Stage>
      <Heading step={1} title="푸는 에이전트" note={EXAMPLE_NOTE} />
      <Floor y={BASE} />
      {/* the spotlight */}
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, opacity: on }}>
        <defs>
          <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#ffe7b0" stopOpacity={0.0} />
            <stop offset="1" stopColor="#ffe7b0" stopOpacity={0.28} />
          </linearGradient>
        </defs>
        <polygon points={`${ROW.orange - 26},150 ${ROW.orange + 26},150 ${ROW.orange + 150},${BASE + 6} ${ROW.orange - 150},${BASE + 6}`} fill="url(#beam)" />
        <ellipse cx={ROW.orange} cy={BASE} rx={160} ry={22} fill="#ffe7b0" opacity={0.22} />
      </svg>
      {SEATS.map((c) => <SeatFig key={c} seat={c} value={START[c]} vmax={VMAX} />)}
      {/* the platform */}
      <div style={{ position: "absolute", left: 1585, top: gbase, width: 300, height: 14, borderRadius: 4, background: "#3a3a46" }} />
      {[1612, 1858].map((x) => <div key={x} style={{ position: "absolute", left: x - 4, top: gbase + 14, width: 8, height: BASE - gbase - 14, background: "#2a2a34" }} />)}
      <Sprite name="guard_aim" x={gx} base={gbase} h={gh} />
      {/* the aim */}
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, opacity: aimIn * (1 - 0.6 * on) }}>
        <line x1={mx} y1={my} x2={tx} y2={ty} stroke={C.red} strokeWidth={4} strokeDasharray="14 12" strokeDashoffset={-frame * 3} opacity={0.9} />
        <circle cx={tx} cy={ty} r={16} fill="none" stroke={C.red} strokeWidth={4} />
        <circle cx={tx} cy={ty} r={4} fill={C.red} />
      </svg>
      <Badge f0={lock + 4} x={ROW.orange} y={BASE - SPR_H - 40} text="solver" bg={C.pink} size={32} />
      {/* the order is not announced */}
      <div style={{ position: "absolute", left: 960 - 330, top: 176, width: 660, display: "flex", alignItems: "center",
        justifyContent: "center", gap: 18, opacity: order, transform: `translateY(${(1 - order) * 12}px)` }}>
        <span style={{ fontSize: T.small, color: C.dim, fontWeight: 600 }}>맡는 순서</span>
        {[0, 1, 2, 3].map((j) => (
          <React.Fragment key={j}>
            <div style={{ width: 54, height: 54, borderRadius: 27, border: "2px dashed rgba(255,255,255,0.3)", display: "grid",
              placeItems: "center", fontSize: 28, fontWeight: 800, color: C.dim }}>?</div>
            {j < 3 ? <span style={{ color: C.faint, fontSize: 26 }}>›</span> : null}
          </React.Fragment>
        ))}
        <span style={{ fontSize: T.small, color: C.pinkSoft, fontWeight: 700 }}>비공개</span>
      </div>
      <Caption />
    </Stage>
  );
};

