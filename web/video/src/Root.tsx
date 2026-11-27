import React from "react";
import { Composition } from "remotion";
import { ArenaRules, Props } from "./ArenaRules";
import { ArenaRulesDrama, DramaProps } from "./ArenaRulesDrama";
import { Trailer, TrailerAnimatic, TrailerFilm } from "./trailer/Trailer";
import { FPS as TRAILER_FPS, TOTAL as TRAILER_TOTAL } from "./trailer/timing";
import { FPS, H, W, buildTimeline } from "./timeline.mjs";
import { loadFonts } from "./fonts";
import narration from "../narration.json";
import media from "./generated/media.json";
import dramaScript from "../narration.drama.json";
import dramaMedia from "./generated/media.drama.json";

loadFonts();

export const RemotionRoot: React.FC = () => {
  const timeline = buildTimeline(narration, media);
  const drama = buildTimeline(dramaScript, dramaMedia);
  return (
    <>
      <Composition id="ArenaRules" component={ArenaRules as React.FC<Props>} width={W} height={H} fps={FPS}
        durationInFrames={timeline.total} defaultProps={{ scenes: timeline.scenes } as Props} />
      <Composition id="ArenaRulesDrama" component={ArenaRulesDrama as React.FC<DramaProps>} width={W} height={H} fps={FPS}
        durationInFrames={drama.total} defaultProps={{ scenes: drama.scenes, total: drama.total, trans: drama.trans } as DramaProps} />
      <Composition id="Trailer" component={Trailer} width={W} height={H} fps={TRAILER_FPS} durationInFrames={TRAILER_TOTAL} />
      <Composition id="TrailerFilm" component={TrailerFilm} width={W} height={H} fps={TRAILER_FPS} durationInFrames={TRAILER_TOTAL} />
      <Composition id="TrailerAnimatic" component={TrailerAnimatic} width={W} height={H} fps={TRAILER_FPS} durationInFrames={TRAILER_TOTAL} />
    </>
  );
};
