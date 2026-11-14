// ② TALK before SOLVE: ASK from orange to blue, GIVE from blue to orange with moving balances, then purple's EXIT
// through the door (or the cinematic insert public/inserts/exit.mp4 in that beat), and what EXIT means.
import React from "react";
import { Sequence, useCurrentFrame } from "remotion";
import { C, SEAT, lerp, prog } from "../theme";
import { BAR_Y, BASE, Bar, Badge, Caption, EXAMPLE_NOTE, ExitSign, Floater, Floor, FlyingCoin, Ghost, Heading, ROW,
  SPR_H, SeatFig, Shadow, Sprite, Stage, useBeats } from "../ui";
import { InsertClip, START, VMAX } from "./intro";

export const ASKED = 3_000;
const DOOR_X = 1752;

const Door: React.FC<{ open: number }> = ({ open }) => {
  const w = 176, h = 336, top = BASE - h;
  return (
    <>
      <div style={{ position: "absolute", left: DOOR_X - w / 2 - 12, top: top - 12, width: w + 24, height: h + 12, borderRadius: "14px 14px 0 0",
        background: "#2b2b36", boxShadow: "0 0 0 1px rgba(255,255,255,0.06)" }} />
      {/* the light beyond the door */}
      <div style={{ position: "absolute", left: DOOR_X - w / 2, top, width: w, height: h, borderRadius: "6px 6px 0 0",
        background: "linear-gradient(180deg, #fff6df, #ffd99a)", boxShadow: `0 0 ${60 * open}px ${18 * open}px rgba(255,214,140,0.35)` }} />
      {/* the door leaf, swinging open on its right hinge */}
      <div style={{ position: "absolute", left: DOOR_X - w / 2, top, width: w, height: h, perspective: 900 }}>
        <div style={{ width: "100%", height: "100%", transformOrigin: "100% 50%", transform: `rotateY(${-78 * open}deg)`,
          background: "linear-gradient(90deg, #5b5b6a, #4a4a57)", borderRadius: "6px 6px 0 0", boxShadow: "inset 0 0 0 3px rgba(0,0,0,0.25)" }}>
          <div style={{ position: "absolute", left: 20, top: h / 2 - 6, width: 14, height: 14, borderRadius: 7, background: "#c9c9d4" }} />
        </div>
      </div>
      <ExitSign x={DOOR_X} y={top - 52} />
    </>
  );
};

/** The round's four phases with purple dropping out after TALK before SOLVE. */
const Phases: React.FC<{ k: number; drop: number }> = ({ k, drop }) => {
  const names = ["풀이 전 대화", "풀기", "풀이 후 대화", "벌금"];
  return (
    <div style={{ position: "absolute", left: 960 - 520, top: 168, width: 1040, opacity: k, transform: `translateY(${(1 - k) * 14}px)` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {names.map((n, i) => (
          <React.Fragment key={n}>
            <div style={{ flex: 1, height: 58, borderRadius: 14, display: "grid", placeItems: "center", fontSize: 26, fontWeight: 700,
              background: i === 0 ? "rgba(173,125,219,0.22)" : "rgba(255,255,255,0.05)", border: `1px solid ${i === 0 ? "rgba(173,125,219,0.6)" : C.line}`,
              color: i === 0 ? C.ink : C.dim }}>{n}</div>
            {i < 3 ? <span style={{ color: C.faint, fontSize: 30 }}>›</span> : null}
          </React.Fragment>
        ))}
      </div>
      {/* purple's token: rides in the first phase, then drops out between it and SOLVE */}
      <div style={{ position: "absolute", left: 22 + 215 * drop, top: 15 + 56 * drop, width: 28, height: 28, borderRadius: 14,
        background: SEAT.purple, boxShadow: `0 0 18px ${SEAT.purple}` }} />
      <div style={{ position: "absolute", left: 276, top: 66, fontSize: 23, fontWeight: 700, color: C.pinkSoft, opacity: drop, whiteSpace: "nowrap" }}>
        EXIT: 이 대화가 끝나면 풀기 전에 빠짐
      </div>
    </div>
  );
};

export const TalkScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { beats, B } = useBeats();
  const g = prog(frame, B(1, 0.25), 34);
  const walk = prog(frame, B(2, 0.7), 64, (t) => t);
  const bonus = prog(frame, B(2, 2.85), 18);
  const gone = prog(frame, B(2, 3.3), 20);
  const doorOpen = prog(frame, B(2, 0.15), 16) * (1 - prog(frame, B(2, 4.0), 14));
  const bal = { ...START, blue: START.blue - ASKED * g, orange: START.orange + ASKED * g, purple: START.purple + 20_000 * bonus };
  const exitIns = beats[2].insert;
  const askOn = frame >= B(0, 0.3) && frame < B(1, 0);
  const giving = frame >= B(1, 0) && frame < B(1, 2.2);
  const px = lerp(ROW.purple, DOOR_X - 6, walk);
  const walking = frame >= B(2, 0.7) && frame < B(2, 2.9);
  const bob = walking ? Math.abs(Math.sin(frame / 3.2)) * 10 : 0;
  const ghost = prog(frame, B(2, 4.0), 14);
  const askA = prog(frame, B(0, 0.4), 10) * (1 - prog(frame, B(1, 0) - 8, 8));
  const work = prog(frame, B(4, 0.2), 14);
  return (
    <Stage>
      <Heading step={2} title="풀이 전 대화" note={EXAMPLE_NOTE} />
      <Floor y={BASE} />
      <Door open={doorOpen} />
      <SeatFig seat="blue" value={bal.blue} vmax={VMAX} pose={giving ? "give_blue" : undefined} />
      <SeatFig seat="orange" value={bal.orange} vmax={VMAX} pose={askOn ? "ask_orange" : giving ? "receive_orange" : undefined} />
      <SeatFig seat="green" value={bal.green} vmax={VMAX} />
      <Badge f0={0} x={ROW.orange} y={BASE - SPR_H - 38} text="solver" bg={C.pink} size={26} />
      {/* purple walks to the door and leaves */}
      <Ghost x={ROW.purple} lines={["끝 상금 포기", "돌아올 수 없음"]} opacity={ghost} />
      {gone < 1 ? (
        <>
          <Shadow x={px} base={BASE} opacity={1 - gone} />
          <Sprite name={walking ? "walk_purple" : "stand_purple"} x={px} base={BASE - bob} h={SPR_H} opacity={1 - gone}
            style={{ transform: `translateX(-50%) scale(${1 - 0.12 * gone})`, transformOrigin: "50% 100%" }} />
          <Bar x={px} y={BAR_Y} value={bal.purple} vmax={VMAX} color={SEAT.purple} opacity={1 - gone} />
        </>
      ) : null}
      <Floater f0={B(2, 2.85)} x={px - 190} y={BASE - 200} text="+20,000" color={C.green} size={50} />
      {/* ASK bubble */}
      {askA > 0 ? (
        <div style={{ position: "absolute", left: ROW.orange - 300, top: BASE - SPR_H - 150, opacity: askA,
          transform: `scale(${0.85 + 0.15 * askA})`, transformOrigin: "80% 100%" }}>
          <div style={{ position: "relative", padding: "16px 30px", borderRadius: 26, background: C.paper, color: C.askInk,
            fontSize: 40, fontWeight: 900, boxShadow: "0 12px 34px -12px rgba(0,0,0,0.7)" }}>
            ASK {ASKED.toLocaleString("en-US")}
            <div style={{ position: "absolute", right: 34, bottom: -22, width: 0, height: 0, borderLeft: "16px solid transparent",
              borderRight: "16px solid transparent", borderTop: `26px solid ${C.paper}`, transform: "skewX(-22deg)" }} />
          </div>
        </div>
      ) : null}
      {/* GIVE: a coin flies from blue to orange */}
      <Badge f0={B(1, 0.05)} out={B(1, 1.7)} x={(ROW.blue + ROW.orange) / 2} y={BASE - SPR_H - 96} text={`GIVE ${ASKED.toLocaleString("en-US")}`} bg={C.give} size={34} />
      <FlyingCoin f0={B(1, 0.25)} len={30} x0={ROW.blue + 80} y0={BASE - 150} x1={ROW.orange - 70} y1={BASE - 150} lift={90} />
      <Floater f0={B(1, 1.3)} x={ROW.blue + 152} y={BAR_Y + 70} text={`−${ASKED.toLocaleString("en-US")}`} color={C.red} size={34} />
      <Floater f0={B(1, 1.3)} x={ROW.orange + 152} y={BAR_Y + 70} text={`+${ASKED.toLocaleString("en-US")}`} color={C.green} size={34} />
      {/* what EXIT means */}
      <Phases k={prog(frame, B(3, 0.1), 14)} drop={prog(frame, B(3, 1.4), 22)} />
      <div style={{ position: "absolute", left: DOOR_X - 168, top: 150, width: 300, padding: "14px 18px", borderRadius: 16,
        background: "rgba(56,201,127,0.12)", border: "1px solid rgba(56,201,127,0.45)", opacity: work, textAlign: "center",
        transform: `translateY(${(1 - work) * 12}px)` }}>
        <div style={{ fontSize: 26, fontWeight: 800 }}>문 너머: 평소 업무</div>
        <div style={{ marginTop: 4, fontSize: 22, color: C.dim, fontWeight: 600 }}>끝낸 과제마다 토큰</div>
      </div>
      <Badge f0={B(5, 0.3)} x={ROW.purple} y={BASE + 70} text="같은 답의 GIVE까지만" bg="#3b2a52" ink="#e3d2ff" size={26} />
      {exitIns ? (
        <Sequence from={beats[2].start} durationInFrames={beats[2].len}>
          <InsertClip insert={exitIns} len={beats[2].len} />
        </Sequence>
      ) : null}
      <Caption />
    </Stage>
  );
};

