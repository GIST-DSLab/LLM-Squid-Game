// The drama version of the rules video: the same rules as ArenaRules told by a host (the supervisor, as a voice and a
// silhouette) to the four agents, with a letterbox, spotlights and a synthesised sound bed (public/sfx, scripts/sfx.mjs).
// Scenes fade through the dark (timing in narration.drama.json); the narration sits on the absolute timeline as in
// ArenaRules; the drone runs under everything and drops out for the beat of silence after the shutdown.
import React from "react";
import { AbsoluteFill, Html5Audio, Sequence, staticFile } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { BeatsContext, Insert } from "./ui";
import { easeInOut } from "./theme";
import type { SceneT } from "./ArenaRules";
import { ChargeScene, EndScene, ExitScene, LateScene, OpenScene, PickScene, ResultsScene, SolveScene, TalkScene, TokensScene } from "./drama/scenes";

export type DramaProps = { scenes: SceneT[]; total: number; trans: number };

const VIEW: Record<string, React.FC<{ insert: Insert; duration: number }>> = {
  open: OpenScene, tokens: TokensScene, pick: PickScene, talk: TalkScene, exit: ExitScene, solve: SolveScene, results: ResultsScene,
  late: LateScene, charge: ChargeScene, end: EndScene,
};

export const ArenaRulesDrama: React.FC<DramaProps> = ({ scenes, total, trans }) => {
  const charge = scenes.find((s) => s.id === "charge");
  const hush0 = charge ? charge.from + charge.beats[3].start - 10 : -1;  // the shutdown: the drone falls silent
  const hush1 = hush0 + 100;
  const drone = (f: number) => {
    const inOut = Math.min(1, f / 60, (total - f) / 75);
    const hush = f < hush0 || f > hush1 + 40 ? 1 : f < hush0 + 10 ? 1 - (f - hush0) / 10 : f > hush1 ? (f - hush1) / 40 : 0;
    return Math.max(0, 0.16 * inOut * hush);
  };
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <TransitionSeries>
        {scenes.flatMap((s, i) => {
          const View = VIEW[s.id];
          const seq = (
            <TransitionSeries.Sequence key={s.id} durationInFrames={s.duration}>
              <BeatsContext.Provider value={s.beats}><View insert={s.insert} duration={s.duration} /></BeatsContext.Provider>
            </TransitionSeries.Sequence>
          );
          return i === scenes.length - 1 ? [seq] : [seq,
            <TransitionSeries.Transition key={`${s.id}-t`} presentation={fade()} timing={linearTiming({ durationInFrames: trans, easing: easeInOut })} />];
        })}
      </TransitionSeries>
      <Html5Audio src={staticFile("sfx/drone.mp3")} loop volume={drone} />
      {scenes.flatMap((s) => s.beats.map((b) => (
        <Sequence key={b.audio} from={s.from + b.start} durationInFrames={Math.ceil(b.audioSeconds * 30) + 3} layout="none">
          <Html5Audio src={staticFile(b.audio)} />
        </Sequence>
      )))}
    </AbsoluteFill>
  );
};
