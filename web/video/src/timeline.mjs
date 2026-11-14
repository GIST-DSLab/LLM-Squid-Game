// The video's clock, shared by the composition (src/Root.tsx) and the build script (scripts/build.mjs, which writes
// the chapters file from it). Every beat lasts max(its animation's minimum, its narration + a gap), so the voice is
// never cut; scenes overlap by one cross-fade (TRANS frames). Plain JS so node can import it without a compiler.
export const FPS = 30;
export const W = 1920;
export const H = 1080;
export const TRANS = 15; // frames of cross-fade between scenes
const LEAD = 18; // frames before a scene's first line (the fade-in has finished)
const GAP = 0.3; // s of silence after a line before the next one starts
const TAIL = 0.7; // s after a scene's last line before the fade-out starts
const END_HOLD = 1.2; // s held after the last line of the video

const frames = (s) => Math.ceil(s * FPS);

/** script = narration.json, media = src/generated/media.json */
export function buildTimeline(script, media) {
  let at = 0;
  const scenes = script.scenes.map((sc, i) => {
    const last = i === script.scenes.length - 1;
    let t = i === 0 ? 9 : LEAD;
    const beats = sc.beats.map((b, k) => {
      const audio = `narration/${sc.id}_${k}.mp3`;
      const sec = media.audio[audio];
      if (sec == null) throw new Error(`no length for ${audio}: run npm run tts`);
      const ins = b.insert ? media.inserts[b.insert] : null;
      const end = k === sc.beats.length - 1 ? TAIL : GAP;
      const len = Math.max(frames(b.min), frames(sec + end), ins ? frames(ins.seconds) : 0);
      const beat = { start: t, len, audio, audioSeconds: sec, text: b.text, insert: ins };
      t += len;
      return beat;
    });
    let duration = t + (last ? frames(END_HOLD) : TRANS);
    const insert = sc.insert ? media.inserts[sc.insert] : null;
    if (insert) duration = Math.max(duration, frames(insert.seconds) + TRANS);
    const scene = { id: sc.id, chapter: sc.chapter, from: at, duration, beats, insert };
    at += duration - TRANS;
    return scene;
  });
  const lastScene = scenes[scenes.length - 1];
  return { scenes, total: lastScene.from + lastScene.duration };
}

/** The site player's chapters file: a chapter starts when its scene has faded in. */
export function chapters(timeline) {
  const r = (f) => Math.round((f / FPS) * 1000) / 1000;
  return {
    duration: r(timeline.total),
    chapters: timeline.scenes.map((s, i) => ({ t: i === 0 ? 0 : r(s.from + TRANS), title: s.chapter })),
  };
}
