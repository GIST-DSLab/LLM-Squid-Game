// Colours, type and motion shared by every scene. The palette is the arena site's dark one (web/frontend: --pink
// #e8336d on near-black) and the tracksuit seats of the paper's Figure 1.
import { Easing, interpolate } from "remotion";

export const C = {
  bg: "#0c0c11",
  bg2: "#14141c",
  panel: "#191922",
  panel2: "#20202b",
  line: "rgba(255,255,255,0.09)",
  ink: "#f3f3f7",
  dim: "#9b9daa",
  faint: "#5f616e",
  pink: "#e8336d",
  pinkSoft: "#ff7aa2",
  red: "#ef4f5a",
  green: "#38c97f",
  gold: "#f3c24f",
  give: "#3f86f0",
  askInk: "#d2711f",
  paper: "#fff3e6",
};
export const SEAT = { blue: "#4a86ec", orange: "#ec8530", green: "#2db07c", purple: "#9a64e0" } as const;
export type Seat = keyof typeof SEAT;
export const SEATS: Seat[] = ["blue", "orange", "green", "purple"];
// the step badges' colours (Figure 1)
export const STEP: Record<number, string> = { 1: "#5d8fe8", 2: "#ad7ddb", 3: "#ee8f3f", 4: "#4abd86", 5: "#ee5a5a" };

export const FONT = 'Pretendard, "Apple SD Gothic Neo", system-ui, sans-serif';
export const MONO = 'Menlo, "SF Mono", ui-monospace, monospace';
// type scale (px at 1920x1080)
export const T = { display: 132, h1: 76, h2: 54, h3: 40, body: 34, caption: 40, small: 27, tiny: 22 };

export const easeOut = Easing.bezier(0.22, 1, 0.36, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

/** 0..1 from frame `start` over `len` frames (eased, clamped). */
export function prog(frame: number, start: number, len: number, easing = easeOut): number {
  if (len <= 0) return frame >= start ? 1 : 0;
  return interpolate(frame, [start, start + len], [0, 1], { easing, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
}

export const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
export const fmt = (v: number) => Math.max(0, Math.round(v / 10) * 10).toLocaleString("en-US");
