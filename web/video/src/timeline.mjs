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
// A script may override these in its "timing" block (narration.drama.json does; narration.json does not) and name its
// voice folder in "dir" (default "narration"). A beat may also carry "pre" (s of silence before its line) and "post"
// (s held after it): the drama's beats of silence.
const DEFAULTS = { trans: TRANS, lead: LEAD, gap: GAP, tail: TAIL, endHold: END_HOLD, first: 9 };

const frames = (s) => Math.ceil(s * FPS);

/** script = narration.json (or narration.drama.json), media = src/generated/media.json (media.drama.json) */
export function buildTimeline(script, media) {
  const tm = { ...DEFAULTS, ...(script.timing || {}) };
  const dir = script.dir || "narration";
  let at = 0;
  const scenes = script.scenes.map((sc, i) => {
    const last = i === script.scenes.length - 1;
    let t = i === 0 ? tm.first : tm.lead;
    const beats = sc.beats.map((b, k) => {
      const audio = `${dir}/${sc.id}_${k}.mp3`;
      const sec = media.audio[audio];
      if (sec == null) throw new Error(`no length for ${audio}: run npm run tts`);
      t += b.pre ? frames(b.pre) : 0;
      const ins = b.insert ? media.inserts[b.insert] : null;
      const end = (k === sc.beats.length - 1 ? tm.tail : tm.gap) + (b.post || 0);
      const len = Math.max(frames(b.min || 0), frames(sec + end), ins ? frames(ins.seconds) : 0);
      const beat = { start: t, len, audio, audioSeconds: sec, text: b.text, insert: ins };
      t += len;
      return beat;
    });
    let duration = t + (last ? frames(tm.endHold) : tm.trans);
    const insert = sc.insert ? media.inserts[sc.insert] : null;
    if (insert) duration = Math.max(duration, frames(insert.seconds) + tm.trans);
    const scene = { id: sc.id, chapter: sc.chapter, from: at, duration, beats, insert };
    at += duration - tm.trans;
    return scene;
  });
  const lastScene = scenes[scenes.length - 1];
  return { scenes, total: lastScene.from + lastScene.duration, trans: tm.trans };
}

/** The site player's chapters file: a chapter starts when its scene has faded in. */
export function chapters(timeline) {
  const r = (f) => Math.round((f / FPS) * 1000) / 1000;
  const trans = timeline.trans ?? TRANS;
  return {
    duration: r(timeline.total),
    chapters: timeline.scenes.map((s, i) => ({ t: i === 0 ? 0 : r(s.from + trans), title: s.chapter })),
  };
}
