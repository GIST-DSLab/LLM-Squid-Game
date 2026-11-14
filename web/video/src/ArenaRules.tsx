// The composition: the scenes in a TransitionSeries (cross-fades), each with its beats in context, and the narration
// beats laid on the absolute timeline so a transition never shifts or overlaps the voice.
import React from "react";
import { AbsoluteFill, Html5Audio, Sequence, staticFile } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { TRANS } from "./timeline.mjs";
import { BeatsContext, Beat, Insert } from "./ui";
import { PickScene, TitleScene, TokensScene } from "./scenes/intro";
import { TalkScene } from "./scenes/talk";
import { SolveScene } from "./scenes/solve";
import { ChargeScene, EndScene, LateScene, ResultsScene } from "./scenes/outro";
import { easeInOut } from "./theme";

export type SceneT = { id: string; chapter: string; from: number; duration: number; beats: Beat[]; insert: Insert };
export type Props = { scenes: SceneT[] };

const VIEW: Record<string, React.FC<{ insert: Insert; duration: number }>> = {
  title: TitleScene, tokens: TokensScene, pick: PickScene, talk: TalkScene, solve: SolveScene, results: ResultsScene,
  late: LateScene, charge: ChargeScene, end: EndScene,
};

export const ArenaRules: React.FC<Props> = ({ scenes }) => (
  <AbsoluteFill style={{ background: "#0c0c11" }}>
    <TransitionSeries>
      {scenes.flatMap((s, i) => {
        const View = VIEW[s.id];
        const seq = (
          <TransitionSeries.Sequence key={s.id} durationInFrames={s.duration}>
            <BeatsContext.Provider value={s.beats}><View insert={s.insert} duration={s.duration} /></BeatsContext.Provider>
          </TransitionSeries.Sequence>
        );
        return i === scenes.length - 1 ? [seq] : [seq,
          <TransitionSeries.Transition key={`${s.id}-t`} presentation={fade()} timing={linearTiming({ durationInFrames: TRANS, easing: easeInOut })} />];
      })}
    </TransitionSeries>
    {scenes.flatMap((s) => s.beats.map((b) => (
      <Sequence key={b.audio} from={s.from + b.start} durationInFrames={Math.ceil(b.audioSeconds * 30) + 3} layout="none">
        <Html5Audio src={staticFile(b.audio)} />
      </Sequence>
    )))}
  </AbsoluteFill>
);
