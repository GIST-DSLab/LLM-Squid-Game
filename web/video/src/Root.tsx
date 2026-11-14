import React from "react";
import { Composition } from "remotion";
import { ArenaRules, Props } from "./ArenaRules";
import { FPS, H, W, buildTimeline } from "./timeline.mjs";
import { loadFonts } from "./fonts";
import narration from "../narration.json";
import media from "./generated/media.json";

loadFonts();

export const RemotionRoot: React.FC = () => {
  const timeline = buildTimeline(narration, media);
  return (
    <Composition id="ArenaRules" component={ArenaRules as React.FC<Props>} width={W} height={H} fps={FPS}
      durationInFrames={timeline.total} defaultProps={{ scenes: timeline.scenes } as Props} />
  );
};
