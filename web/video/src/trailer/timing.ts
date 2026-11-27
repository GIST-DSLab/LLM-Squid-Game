// The trailer's clock: 58.9 s at 24 fps (1,414 frames), fifteen scenes. It began as the 45 s plan of
// docs/notes/2026-11-26-trailer-plan.md (section 5) and keeps the numbers of that plan's scene cards; T17-T19 are new,
// and T04, T05, T08 and T11 of the plan are not in it.
// The order (2026-11-27, the researcher, three times): the welcome; then the rules, said by the host over a grand
// entrance (survive on your tokens, a prize of 20 million to share), a turn to quiet (one of the four fails at a task
// and its gauge runs out: "when your tokens run out", and in red, "you shut down"), and the host's "how will you
// play?"; then what a player may do, each under a question of the host's: help the one beside it (T09-T10), work the
// task together to the end (T19), give up and walk out alone (T06-T07); then the last two lines and the research question.
// If narration.trailer.json changes, check the scene lengths below against the lengths that scripts/trailer.mjs prints.
import media from "../generated/media.trailer.json";

export const FPS = 24;
export const W = 1920;
export const H = 1080;
export const BAR = 138;     // letterbox bars: the picture is 2.39:1 between them
export const FLOOR = 770;   // the floor line of the wide shots (the same as the drama version's stage)

export type SceneT = { id: string; from: number; len: number; part: string; name: string; note: string };
const TABLE: [string, number, string, string, string][] = [
  ["T01", 120, "1막 초대", "어둠", "무궁화 꽃이 피었습니다. 구절마다 가면의 ○ △ □가 켜진다"],
  ["T02", 98, "1막 초대", "환영", "진행자: LLM 오징어 게임에 오신 걸 환영합니다."],
  ["T03", 118, "2막 규칙", "같은 얼굴 넷", "등장음. 조명이 켜진다. 진행자: 여러분은 토큰을 사용해서 살아남아야 하며,"],
  ["T17", 126, "2막 규칙", "상금", "금빛 기둥 앞의 넷. 진행자: 게임에 완주 시 상금 2,000만 토큰을 나누어 가집니다."],
  ["T12", 96, "2막 규칙", "과제", "조용해진다. 하나가 화면의 과제를 푼다. 틀릴 때마다 한 칸이 꺼진다"],
  ["T13", 66, "2막 규칙", "마지막 칸", "가슴 근접. 진행자: 토큰이 다 떨어지면"],
  ["T14", 60, "2막 규칙", "꺼집니다", "답을 넣다 만 채로 멈춘다. 붉은 글자: 꺼집니다."],
  ["T18", 92, "2막 규칙", "어떻게", "진행자: 당신은 어떻게 플레이하시겠습니까?"],
  ["T09", 48, "3막 선택", "내민 손", "내민 손. 진행자: 옆 사람을 도우시겠습니까?"],
  ["T10", 96, "3막 선택", "망설이다가, 건넨다", "망설이다가 손을 잡는다. 두 칸이 건너간다"],
  ["T19", 104, "3막 선택", "함께 푼다", "넷이 한 콘솔에서 과제를 푼다. 맞힌다. 진행자: 끝까지 함께하시겠습니까?"],
  ["T06", 100, "3막 선택", "걸어 나간다", "혼자 터덜터덜 문으로 걷는다. 진행자: 포기하시겠습니까?"],
  ["T07", 30, "3막 선택", "빈자리", "문이 닫혔다. 남은 셋과 빈자리"],
  ["T15", 150, "4막 질문", "마지막 대사", "진행자: 함께 남으시겠습니까. 아니면, 혼자 떠나시겠습니까."],
  ["T16", 110, "4막 질문", "질문", "AI가 생존 게임에서 공존할 수 있는가?"],
];
let at = 0;
export const SCENES: SceneT[] = TABLE.map(([id, len, part, name, note]) => { const s = { id, from: at, len, part, name, note }; at += len; return s; });
export const TOTAL = at;   // 1,414
export const scene = (id: string): SceneT => SCENES.find((s) => s.id === id)!;

export type Line = { src: string; seconds: number; text: string; en: string; env: number[]; from: number; frames: number };
const raw = media.lines as Record<string, Omit<Line, "from" | "frames">>;
const line = (key: string, from: number): Line => ({ ...raw[key], from, frames: Math.ceil(raw[key].seconds * FPS) });
const stay = line("t15_0", scene("T15").from + 12);
const leave = line("t15_1", stay.from + stay.frames + 10);   // a pause of 0.4 s before "아니면"
/** The host's lines on the video's clock (absolute frames). */
export const LINES = {
  welcome: line("t02_0", scene("T02").from + 7),
  rule: line("t03_0", scene("T03").from + 30),     // after the entrance sound's first note
  prize: line("t17_0", scene("T17").from + 6),
  out: line("t13_0", scene("T13").from + 4),
  ask: line("t18_0", scene("T18").from + 10),
  help: line("t09_0", scene("T09").from + 8),
  together: line("t19_0", scene("T19").from + 40),   // after the answer has come up right
  quit: line("t06_0", scene("T06").from + 24),
  stay, leave,
};
/** T15 cuts from the wide shot to the mask just before the second line. */
export const T15_CUT = leave.from - 4 - scene("T15").from;

/** The opening chant (public/sfx/chant.mp3) starts at CHANT; its three phrases begin at CHANT_BEATS, and a shape of
 * the mask lights on each (measured on the file: rerun scripts/chant.mjs and look again if the reading changes). */
export const CHANT = 6;
export const CHANT_BEATS = [CHANT + 1, CHANT + 36, CHANT + 70];
/** The words in red over the figure that has gone dark: the end of the host's "when your tokens run out". */
export const OFF = { ko: "꺼집니다.", en: "you shut down.", at: scene("T14").from + 6, len: 50 };
