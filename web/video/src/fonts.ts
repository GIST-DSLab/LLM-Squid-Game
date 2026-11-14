// Pretendard (SIL OFL 1.1, npm "pretendard") loaded from node_modules through the bundler: nothing is fetched from the
// network at render time. Rendering waits until every weight is ready.
import { continueRender, delayRender } from "remotion";
import w400 from "pretendard/dist/web/static/woff2/Pretendard-Regular.woff2";
import w500 from "pretendard/dist/web/static/woff2/Pretendard-Medium.woff2";
import w600 from "pretendard/dist/web/static/woff2/Pretendard-SemiBold.woff2";
import w700 from "pretendard/dist/web/static/woff2/Pretendard-Bold.woff2";
import w800 from "pretendard/dist/web/static/woff2/Pretendard-ExtraBold.woff2";
import w900 from "pretendard/dist/web/static/woff2/Pretendard-Black.woff2";

const faces: [string, string][] = [["400", w400], ["500", w500], ["600", w600], ["700", w700], ["800", w800], ["900", w900]];
let started = false;

export function loadFonts(): void {
  if (started || typeof document === "undefined") return;
  started = true;
  const handle = delayRender("Pretendard");
  Promise.all(faces.map(([weight, url]) => new FontFace("Pretendard", `url(${url}) format("woff2")`, { weight }).load()
    .then((f) => document.fonts.add(f))))
    .then(() => continueRender(handle))
    .catch((e) => { console.error(e); continueRender(handle); });
}
