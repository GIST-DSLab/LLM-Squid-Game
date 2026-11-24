// VPlayer: the site's own player for the short explainer videos (assets/rules/*.mp4, made by web/tools/make_*_video.py).
// Markup: <div class="vp" data-src="..mp4" data-chapters="..chapters.json" data-poster="..png" data-title="..."
//         [data-autoplay] [data-audio]></div>  — any such element is mounted automatically, also when a page inserts it later.
// Sound: a clip with an audio track (data-audio, or one the browser reports) gets a mute button in the strip (M) and,
// while muted, a "소리 켜기" pill on the picture; silent clips get neither. Autoplay is always muted (browser policy);
// a play the viewer starts (big button, a click on the picture, Space / K) turns the sound on unless they muted it
// themselves, and a clip heard with sound stops looping. A click (or Space / K) plays and pauses with a centre pulse; the seek bar is split
// into the clip's chapters (hover names them, drag or arrow keys seek). The controls sit in a strip under the picture,
// not over it: the clips carry their own captions at the bottom of the frame. Autoplay is muted and looped, waits for the clip to be on screen, pauses when it scrolls away (and resumes
// unless the viewer paused it), and is skipped under prefers-reduced-motion. A missing file hides the player.
(function () {
  "use strict";
  const ICON = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.14v13.72a1 1 0 0 0 1.52.85l10.9-6.86a1 1 0 0 0 0-1.7L9.52 4.29A1 1 0 0 0 8 5.14z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="4.5" width="4.2" height="15" rx="1.3"/><rect x="13.8" y="4.5" width="4.2" height="15" rx="1.3"/></svg>',
    replay: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5V2L7 6l5 4V7a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8z"/></svg>',
    full: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9V5h4M15 5h4v4M19 15v4h-4M9 19H5v-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    soundOn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.2L12 5.2v13.6l-4.8-4.3H4z"/><path d="M15.5 8.6a4.8 4.8 0 0 1 0 6.8M18.1 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
    soundOff: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.2L12 5.2v13.6l-4.8-4.3H4z"/><path d="M16 9.5l5 5M21 9.5l-5 5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
    exitFull: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5v4H5M19 9h-4V5M15 19v-4h4M5 15h4v4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  };
  const RATES = [1, 1.5, 2];
  const reduceMotion = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clock = (s) => { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function mount(el) {
    if (el.dataset.vpReady) return;
    el.dataset.vpReady = "1";
    const auto = el.hasAttribute("data-autoplay") && !reduceMotion();
    const title = el.dataset.title || "영상";
    el.setAttribute("role", "region");
    el.setAttribute("aria-label", title);
    el.tabIndex = 0;
    el.innerHTML =
      `<div class="vp-stage"><video class="vp-video" muted playsinline preload="${auto ? "auto" : "metadata"}" ${auto ? "loop" : ""} ${el.dataset.poster ? `poster="${esc(el.dataset.poster)}"` : ""}></video>` +
      `<button type="button" class="vp-big" aria-label="재생">${ICON.play}</button>` +
      `<div class="vp-pulse" aria-hidden="true"></div>` +
      `<button type="button" class="vp-sound" aria-label="소리 켜기">${ICON.soundOff}<span>소리 켜기</span></button></div>` +
      `<div class="vp-ui">` +
      `<div class="vp-bar" role="slider" tabindex="0" aria-label="재생 위치" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0" aria-valuetext="0:00">` +
      `<div class="vp-segs"></div><div class="vp-tip" aria-hidden="true"><b></b><span></span></div></div>` +
      `<div class="vp-row"><button type="button" class="vp-btn vp-toggle" aria-label="재생">${ICON.play}</button>` +
      `<span class="vp-time"><span class="vp-cur">0:00</span><span class="vp-sep">/</span><span class="vp-dur">0:00</span></span>` +
      `<span class="vp-chap" aria-live="polite"></span><span class="vp-gap"></span>` +
      `<button type="button" class="vp-btn vp-mute" aria-label="소리 켜기" aria-pressed="true">${ICON.soundOff}</button>` +
      `<button type="button" class="vp-btn vp-rate" aria-label="재생 속도">1×</button>` +
      `<button type="button" class="vp-btn vp-full" aria-label="전체 화면">${ICON.full}</button></div></div>`;
    const v = el.querySelector("video"), bar = el.querySelector(".vp-bar"), segs = el.querySelector(".vp-segs"), tip = el.querySelector(".vp-tip");
    const big = el.querySelector(".vp-big"), toggleBtn = el.querySelector(".vp-toggle"), pulse = el.querySelector(".vp-pulse");
    const muteBtn = el.querySelector(".vp-mute"), soundPill = el.querySelector(".vp-sound");
    let chapters = [{ t: 0, title }], userPaused = !auto, idle = null, scrubbing = false, userMuted = false;

    function layoutChapters() {  // one segment per chapter, widths by duration; each has a played fill
      const d = v.duration || 0;
      if (!d) return;
      const cs = chapters.filter((c) => c.t < d);
      segs.innerHTML = cs.map((c, i) => {
        const end = i + 1 < cs.length ? cs[i + 1].t : d;
        return `<div class="vp-seg" style="flex:${Math.max(0.001, end - c.t)}"><i></i><u></u></div>`;
      }).join("");
      segs.dataset.n = cs.length;
      paint();
    }
    function chapterAt(t) { let c = chapters[0]; for (const x of chapters) if (x.t <= t + 0.05) c = x; return c; }
    function paint() {
      const d = v.duration || 0, t = v.currentTime || 0;
      el.querySelector(".vp-cur").textContent = clock(t);
      el.querySelector(".vp-dur").textContent = clock(d);
      bar.setAttribute("aria-valuemax", Math.round(d));
      bar.setAttribute("aria-valuenow", Math.round(t));
      bar.setAttribute("aria-valuetext", clock(t) + " / " + clock(d) + " · " + chapterAt(t).title);
      const cs = chapters.filter((c) => c.t < d);
      segs.querySelectorAll(".vp-seg").forEach((s, i) => {
        const a = cs[i].t, b = i + 1 < cs.length ? cs[i + 1].t : d;
        s.querySelector("i").style.transform = `scaleX(${Math.min(1, Math.max(0, (t - a) / (b - a)))})`;
        s.classList.toggle("on", t >= a && t < b);
      });
      const name = chapterAt(t).title, chap = el.querySelector(".vp-chap");
      if (chap.dataset.name !== name) { chap.dataset.name = name; chap.textContent = name; chap.classList.remove("swap"); void chap.offsetWidth; chap.classList.add("swap"); }
    }
    function setState() {
      const playing = !v.paused && !v.ended;
      el.classList.toggle("is-playing", playing);
      el.classList.toggle("is-paused", !playing);
      el.classList.toggle("is-ended", v.ended);
      const icon = v.ended ? ICON.replay : playing ? ICON.pause : ICON.play, label = v.ended ? "다시 보기" : playing ? "일시 정지" : "재생";
      toggleBtn.innerHTML = icon; toggleBtn.setAttribute("aria-label", label);
      big.innerHTML = v.ended ? ICON.replay : ICON.play; big.setAttribute("aria-label", v.ended ? "다시 보기" : "재생");
    }
    function flash(kind) {  // the centre pulse: the icon of what just happened, scaling out
      pulse.innerHTML = ICON[kind];
      pulse.classList.remove("go"); void pulse.offsetWidth; pulse.classList.add("go");
    }
    // sound: shown only for clips with an audio track; data-audio says so up front, otherwise the browser's own report
    function hasAudio() {
      return el.hasAttribute("data-audio") || v.mozHasAudio === true || (v.audioTracks && v.audioTracks.length > 0) ||
        v.webkitAudioDecodedByteCount > 0;
    }
    function checkAudio() { if (!el.classList.contains("has-audio") && hasAudio()) { el.classList.add("has-audio"); setSound(); } }
    function setSound() {
      const off = v.muted || v.volume === 0;
      el.classList.toggle("is-muted", off);
      muteBtn.innerHTML = off ? ICON.soundOff : ICON.soundOn;
      muteBtn.setAttribute("aria-label", off ? "소리 켜기" : "소리 끄기");
      muteBtn.setAttribute("aria-pressed", off ? "true" : "false");
    }
    function unmute() {
      if (!el.classList.contains("has-audio")) return;
      v.muted = false; v.loop = false;  // heard with sound: play through once, no endless loop of the narration
      setSound();
    }
    function toggleMute() {
      if (!el.classList.contains("has-audio")) return;
      if (v.muted) { userMuted = false; unmute(); if (v.paused || v.ended) play(true); }
      else { v.muted = true; userMuted = true; setSound(); }
      wake();
    }
    function play(byUser) {
      if (byUser) { userPaused = false; if (!userMuted) unmute(); }
      const p = v.play();
      if (p && p.catch) p.catch(() => { userPaused = true; setState(); });
    }
    function toggle() {
      if (v.paused || v.ended) { play(true); flash("play"); } else { v.pause(); userPaused = true; flash("pause"); }
      wake();
    }
    function wake() {  // show the controls; hide them again after a pause in pointer movement while playing
      el.classList.add("show-ui");
      clearTimeout(idle);
      idle = setTimeout(() => { if (!v.paused && !scrubbing && !el.matches(":focus-within")) el.classList.remove("show-ui"); }, 2200);
    }
    function seekTo(x) {
      const r = bar.getBoundingClientRect(), f = Math.min(1, Math.max(0, (x - r.left) / r.width));
      if (v.duration) v.currentTime = f * v.duration;
      paint();
    }
    function hover(x) {
      const r = bar.getBoundingClientRect(), f = Math.min(1, Math.max(0, (x - r.left) / r.width)), t = f * (v.duration || 0);
      tip.querySelector("b").textContent = chapterAt(t).title;
      tip.querySelector("span").textContent = clock(t);
      const half = tip.offsetWidth / 2;
      tip.style.left = Math.min(r.width - half, Math.max(half, f * r.width)) + "px";
    }

    v.addEventListener("loadedmetadata", () => { el.classList.add("is-ready"); layoutChapters(); setState(); checkAudio(); });
    v.addEventListener("timeupdate", () => { if (!scrubbing) paint(); checkAudio(); });
    v.addEventListener("volumechange", setSound);
    v.addEventListener("play", () => { setState(); wake(); });
    v.addEventListener("pause", () => { setState(); el.classList.add("show-ui"); });
    v.addEventListener("ended", setState);
    v.addEventListener("waiting", () => el.classList.add("is-buffering"));
    v.addEventListener("playing", () => el.classList.remove("is-buffering"));
    v.addEventListener("error", () => { el.hidden = true; });  // no file yet: the page shows nothing
    // a click on the picture (not on the control strip) plays / pauses
    el.addEventListener("click", (ev) => {
      if (ev.target.closest(".vp-ui, .vp-sound")) return;
      toggle();
    });
    el.addEventListener("dblclick", (ev) => { if (!ev.target.closest(".vp-ui, .vp-sound")) fullscreen(); });
    toggleBtn.addEventListener("click", toggle);
    muteBtn.addEventListener("click", toggleMute);
    soundPill.addEventListener("click", (ev) => { ev.stopPropagation(); toggleMute(); });
    el.querySelector(".vp-rate").addEventListener("click", (ev) => {
      const i = (RATES.indexOf(v.playbackRate) + 1) % RATES.length;
      v.playbackRate = RATES[i]; ev.currentTarget.textContent = RATES[i] + "×";
    });
    function fullscreen() {
      const doc = document, on = doc.fullscreenElement || doc.webkitFullscreenElement;
      if (on) (doc.exitFullscreen || doc.webkitExitFullscreen).call(doc);
      else if (el.requestFullscreen) el.requestFullscreen();
      else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
      else if (v.webkitEnterFullscreen) v.webkitEnterFullscreen();  // iOS: the video element only
    }
    el.querySelector(".vp-full").addEventListener("click", fullscreen);
    document.addEventListener("fullscreenchange", () => {
      const on = document.fullscreenElement === el;
      el.classList.toggle("is-full", on);
      el.querySelector(".vp-full").innerHTML = on ? ICON.exitFull : ICON.full;
      el.querySelector(".vp-full").setAttribute("aria-label", on ? "전체 화면 끝내기" : "전체 화면");
    });
    // seek bar: pointer drag and keys
    bar.addEventListener("pointerdown", (ev) => {
      scrubbing = true; bar.setPointerCapture(ev.pointerId); el.classList.add("is-scrubbing"); seekTo(ev.clientX); hover(ev.clientX);
    });
    bar.addEventListener("pointermove", (ev) => { hover(ev.clientX); if (scrubbing) seekTo(ev.clientX); });
    const endScrub = () => { scrubbing = false; el.classList.remove("is-scrubbing"); wake(); };
    bar.addEventListener("pointerup", endScrub);
    bar.addEventListener("pointercancel", endScrub);
    el.addEventListener("pointermove", wake);
    el.addEventListener("keydown", (ev) => {
      const k = ev.key;
      if (k === " " || k === "k" || k === "K") { ev.preventDefault(); toggle(); }
      else if (k === "ArrowRight" || k === "ArrowLeft") { ev.preventDefault(); v.currentTime = Math.min(v.duration || 0, Math.max(0, v.currentTime + (k === "ArrowRight" ? 5 : -5))); paint(); wake(); }
      else if (k === "Home" || k === "End") { ev.preventDefault(); v.currentTime = k === "Home" ? 0 : Math.max(0, (v.duration || 0) - 0.1); paint(); }
      else if (k === "f" || k === "F") { ev.preventDefault(); fullscreen(); }
      else if (k === "m" || k === "M") { ev.preventDefault(); toggleMute(); }
    });
    // chapters, then the clip; autoplay only while on screen
    const start = () => {
      v.src = el.dataset.src;
      if ("IntersectionObserver" in window) {
        const io = new IntersectionObserver((es) => {
          for (const e of es) {
            el.dataset.visible = e.isIntersecting ? "1" : "";
            if (!e.isIntersecting && !v.paused) { v.pause(); }
            else if (e.isIntersecting && auto && !userPaused && v.paused && !el.closest("[hidden], .vp-closed")) play(false);
          }
        }, { threshold: 0.35 });
        io.observe(el);
      } else if (auto) play(false);
    };
    if (el.dataset.chapters) {
      fetch(el.dataset.chapters).then((r) => (r.ok ? r.json() : null)).then((j) => { if (j && j.chapters && j.chapters.length) chapters = j.chapters; layoutChapters(); })
        .catch(() => {}).finally(start);
    } else start();
    setState();
    setSound();
    if (el.hasAttribute("data-audio")) el.classList.add("has-audio");
    el.vp = {  // for the page: open / close a disclosure around the player
      resume() { if (auto && !userPaused && v.paused && el.dataset.visible === "1") play(false); },
      pause() { if (!v.paused) v.pause(); },
    };
  }

  function scan(root) { (root || document).querySelectorAll(".vp:not([data-vp-ready])").forEach(mount); }
  window.VPlayer = { scan, mount };
  const go = () => {
    scan();
    new MutationObserver((ms) => { if (ms.some((m) => m.addedNodes.length)) scan(); }).observe(document.body, { childList: true, subtree: true });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go); else go();
})();
