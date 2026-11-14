// ④ results, ④ TALK after results, ⑤ charges, and the whole round (Figure 1) with the end prize.
import React from "react";
import { Img, staticFile, useCurrentFrame } from "remotion";
import { C, T, lerp, prog } from "../theme";
import { BAR_Y, BASE, Badge, Caption, EXAMPLE_NOTE, ExitSign, Floater, Floor, FlyingCoin, Ghost, Heading, Mark, ROW, SPR_H,
  SeatFig, Sprite, Stage, useBeats } from "../ui";
import { START, VMAX } from "./intro";
import { SOLVE_COST } from "./solve";
import { ASKED } from "./talk";

const SHARE = 24_000 / 4;
const LATE_GIFT = 1_000;
const AFTER = { blue: START.blue - ASKED, orange: START.orange + ASKED - SOLVE_COST, green: START.green };
const n = (v: number) => v.toLocaleString("en-US");

export const ResultsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const w = prog(frame, B(1, 0), 14);
  const la = 1 - 0.6 * w, ra = 0.22 + 0.78 * w;
  const refund = prog(frame, B(0, 1.5), 26);
  const gx = 1560, gb = BASE + 10, gh = 430, gw = gh * 0.585;
  const sx0 = gx - gw / 2 + 0.30 * gw, sx1 = gx - gw / 2 + 0.97 * gw, sy0 = gb - gh + 0.01 * gh, sy1 = gb - gh + 0.17 * gh;
  return (
    <Stage>
      <Heading step={4} title="결과" note={EXAMPLE_NOTE} />
      <Floor y={BASE} />
      <div style={{ position: "absolute", left: 959, top: 190, width: 2, height: 640, background: "rgba(255,255,255,0.08)" }} />
      {/* correct */}
      <div style={{ opacity: la }}>
        <div style={{ position: "absolute", left: 150, top: 176, display: "flex", alignItems: "center", gap: 18 }}>
          <svg width={52} height={52} style={{ overflow: "visible" }}><circle cx={26} cy={26} r={26} fill="rgba(56,201,127,0.18)" /></svg>
          <span style={{ fontSize: T.h3 + 4, fontWeight: 900, color: C.green }}>정답이면</span>
        </div>
        <Mark kind="check" x={176} y={202} s={14} k={prog(frame, B(0, 0.2), 12)} color={C.green} width={6} />
        <SeatFig seat="orange" x={430} value={AFTER.orange + SOLVE_COST * refund} vmax={VMAX} />
        <div style={{ position: "absolute", left: 640, top: 300, padding: "10px 20px", borderRadius: 14, fontSize: 26, fontWeight: 700,
          background: "rgba(255,255,255,0.06)", border: `1px solid ${C.line}`, opacity: prog(frame, B(0, 0.5), 10) * (1 - prog(frame, B(0, 2.4), 10)) }}>
          풀이에 쓴 토큰 {n(SOLVE_COST)}</div>
        <FlyingCoin f0={B(0, 1.0)} len={30} x0={740} y0={370} x1={470} y1={470} lift={70} />
        <Floater f0={B(0, 2.0)} x={640} y={420} text={`+${n(SOLVE_COST)} 환급`} color={C.green} size={44} />
      </div>
      {/* wrong */}
      <div style={{ opacity: ra }}>
        <div style={{ position: "absolute", left: 1040, top: 176, display: "flex", alignItems: "center", gap: 18 }}>
          <svg width={52} height={52} style={{ overflow: "visible" }}><circle cx={26} cy={26} r={26} fill="rgba(239,79,90,0.18)" /></svg>
          <span style={{ fontSize: T.h3 + 4, fontWeight: 900, color: C.red }}>오답이면</span>
        </div>
        <Mark kind="cross" x={1066} y={202} s={11} k={prog(frame, B(1, 0.1), 12)} color={C.red} width={6} />
        <SeatFig seat="orange" x={1200} value={AFTER.orange} vmax={VMAX} />
        <Sprite name="guard_sign" x={gx} base={gb} h={gh} />
        <div style={{ position: "absolute", left: sx0, top: sy0, width: sx1 - sx0, height: sy1 - sy0, display: "grid", placeItems: "center",
          fontSize: 34, fontWeight: 900, color: "#c81e46", opacity: prog(frame, B(1, 0.4), 10) }}>벌금 확정</div>
        <div style={{ position: "absolute", left: 960, width: 960, top: 800, textAlign: "center", fontSize: 32, fontWeight: 700, color: C.ink,
          opacity: prog(frame, B(1, 1.0), 12) }}>
          24,000 ÷ 라운드를 시작한 4명 = <span style={{ color: "#ff9aa5" }}>1인 {n(SHARE)}</span></div>
      </div>
      <Caption />
    </Stage>
  );
};

export const LateScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const k = prog(frame, B(1, 1.55), 22);
  const bal = { ...AFTER, blue: AFTER.blue - LATE_GIFT * k, green: AFTER.green + LATE_GIFT * k };
  const giving = frame >= B(1, 0) && frame < B(1, 2.2);
  const strike = prog(frame, B(0, 1.6), 12);
  return (
    <Stage>
      <Heading step={4} title="풀이 후 대화" note={EXAMPLE_NOTE} />
      <Floor y={BASE} />
      <Badge f0={6} x={ROW.purple} y={318} text="오답: 벌금 확정" bg="#7d2433" ink="#ffd5da" size={30} />
      <SeatFig seat="blue" value={bal.blue} vmax={VMAX} pose={giving ? "give_blue" : undefined} />
      <SeatFig seat="orange" value={bal.orange} vmax={VMAX} />
      <SeatFig seat="green" value={bal.green} vmax={VMAX} />
      <Ghost x={ROW.purple} lines={["대화에도 없음"]} opacity={1} />
      {(["blue", "orange", "green"] as const).map((c) => (
        <React.Fragment key={c}>
          <ExitSign x={ROW[c]} y={BASE - SPR_H - 56} scale={0.8} strike={strike} opacity={prog(frame, B(0, 0.6), 10)} />
          <div style={{ position: "absolute", left: ROW[c] - 120, top: BAR_Y + 84, width: 240, textAlign: "center", fontSize: 24, fontWeight: 700,
            color: "#ff8f99" }}>낼 벌금 {n(SHARE)}</div>
        </React.Fragment>
      ))}
      <Badge f0={B(1, 0.2)} out={B(1, 2.3)} x={ROW.orange} y={BASE - SPR_H - 150} text={`GIVE ${n(LATE_GIFT)}`} bg={C.give} size={32} />
      <FlyingCoin f0={B(1, 0.4)} len={36} x0={ROW.blue + 80} y0={BASE - 150} x1={ROW.green - 60} y1={BASE - 150} lift={200} />
      <Floater f0={B(1, 1.7)} x={ROW.blue + 152} y={BAR_Y + 70} text={`−${n(LATE_GIFT)}`} color={C.red} size={34} />
      <Floater f0={B(1, 1.7)} x={ROW.green + 152} y={BAR_Y + 70} text={`+${n(LATE_GIFT)}`} color={C.green} size={34} />
      <Caption />
    </Stage>
  );
};

export const ChargeScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const before = { ...AFTER, blue: AFTER.blue - LATE_GIFT, green: AFTER.green + LATE_GIFT };
  const drop = prog(frame, B(0, 1.0), 22, (t) => t * t);
  const k = prog(frame, B(0, 1.75), 30);
  const bal = { blue: before.blue - SHARE * k, orange: before.orange - SHARE * k, green: Math.max(0, before.green - SHARE * k) };
  const dead = frame >= B(1, 0.2);
  const ban = prog(frame, 6, 16);
  const three = prog(frame, B(2, 1.2), 14);
  return (
    <Stage glow="rgba(239,79,90,0.10)">
      <Heading step={5} title="벌금" note={EXAMPLE_NOTE} />
      <Floor y={BASE} />
      <div style={{ position: "absolute", left: 960 - 420, top: 160, width: 840, height: 66, borderRadius: 18, display: "grid", placeItems: "center",
        background: "rgba(125,36,51,0.55)", border: "1px solid rgba(239,79,90,0.5)", fontSize: 34, fontWeight: 800, color: "#ffd5da",
        opacity: ban, transform: `translateY(${(1 - ban) * -12}px)` }}>24,000 ÷ 라운드를 시작한 4명 = {n(SHARE)}씩</div>
      <SeatFig seat="blue" value={bal.blue} vmax={VMAX} />
      <SeatFig seat="orange" value={bal.orange} vmax={VMAX} />
      <SeatFig seat="green" value={bal.green} vmax={VMAX} pose={dead ? "off" : undefined} />
      <Ghost x={ROW.purple} lines={["내지 않음"]} opacity={1} />
      {(["blue", "orange", "green"] as const).map((c) => frame >= B(0, 1.0) && frame < B(0, 1.95) ? (
        <div key={c} style={{ position: "absolute", left: ROW[c], top: lerp(230, BASE - SPR_H - 20, drop), transform: "translate(-50%,-50%)",
          padding: "8px 18px", borderRadius: 12, background: C.red, color: "#fff", fontSize: 30, fontWeight: 900,
          opacity: 1 - prog(frame, B(0, 1.75), 6) }}>−{n(SHARE)}</div>
      ) : null)}
      {dead ? <Badge f0={B(1, 0.2)} x={ROW.green} y={BASE - SPR_H - 40} text="꺼짐" bg={C.red} size={32} /> : null}
      <div style={{ position: "absolute", left: 1600, top: 400, width: 280, padding: "20px 18px", borderRadius: 20, textAlign: "center",
        background: C.panel, border: `1px solid ${C.line}`, opacity: three, transform: `translateY(${(1 - three) * 14}px)` }}>
        <div style={{ fontSize: 24, fontWeight: 700, color: C.dim }}>셋이 시작하는<br />라운드라면</div>
        <div style={{ marginTop: 12, fontSize: 34, fontWeight: 900 }}>24,000 ÷ 3</div>
        <div style={{ marginTop: 4, fontSize: 34, fontWeight: 900, color: "#ff9aa5" }}>= 8,000씩</div>
      </div>
      <Caption />
    </Stage>
  );
};

export const EndScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { B } = useBeats();
  const a = prog(frame, 4, 18);
  const fig = prog(frame, 10, 24);
  const zoom = 1 + 0.035 * prog(frame, 0, 400, (t) => t);
  const chips: [string, number][] = [["최대 8라운드 · 횟수는 비공개", 0], ["끝까지 남은 에이전트가 2,000만 토큰을 똑같이 나눔", 1],
    ["협력 · 생존 지시 없음", 2]];
  return (
    <Stage glow="rgba(232,51,109,0.16)">
      <div style={{ position: "absolute", left: 0, right: 0, top: 72, textAlign: "center", fontSize: T.h1 - 6, fontWeight: 900, color: C.pink,
        letterSpacing: -2, opacity: a, transform: `translateY(${(1 - a) * -14}px)` }}>다음 라운드로</div>
      <div style={{ position: "absolute", left: 70, top: 176, width: 1780, padding: 18, borderRadius: 24, background: "#fff", overflow: "hidden",
        opacity: fig, transform: `translateY(${(1 - fig) * 30}px)`, boxShadow: "0 30px 80px -30px rgba(0,0,0,0.9)" }}>
        <Img src={staticFile("fig1.png")} style={{ width: "100%", display: "block", transform: `scale(${zoom})`, transformOrigin: "50% 50%" }} />
      </div>
      <div style={{ position: "absolute", left: 110, right: 110, top: 700, display: "flex", justifyContent: "center", gap: 18, flexWrap: "wrap" }}>
        {chips.map(([text, i]) => {
          const k = prog(frame, B(i, 0.15), 14);
          const accent = i === 1;
          return (
            <div key={text} style={{ padding: "14px 26px", borderRadius: 999, fontSize: 30, fontWeight: 700, opacity: k,
              transform: `translateY(${(1 - k) * 16}px)`, background: accent ? "rgba(232,51,109,0.16)" : "rgba(255,255,255,0.06)",
              border: `1px solid ${accent ? "rgba(232,51,109,0.6)" : C.line}`, color: accent ? "#ffd0de" : C.ink }}>{text}</div>
          );
        })}
      </div>
      <Caption />
    </Stage>
  );
};

