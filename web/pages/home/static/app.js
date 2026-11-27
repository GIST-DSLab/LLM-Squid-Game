// LLM Squid Game — landing page logic.
//
// Pure vanilla JS + Alpine.js (CDN). No build step. The landing never talks
// to a backend: this file keeps only the #home/#about tab store, the
// scroll-reveal observer and the trailer box. (The self-playing rules demo of the old benchmark
// page and its display helpers went with that page's explainer, 2026-11-26.)

(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // #home is the landing: hero + the explainer bands; #about shows the
  // explainer on its own. Only the two static tabs remain; the legacy #play/#arena/#leaderboard/
  // #logs anchors (and #models) fall back to #home.
  const APP_TABS = ["home", "about"];

  function tabFromHash() {
    const h = (location.hash || "").replace("#", "");
    return APP_TABS.indexOf(h) !== -1 ? h : "home";
  }

  document.addEventListener("alpine:init", () => {
    Alpine.store("nav", {
      tab: tabFromHash(),
      setFromHash() {
        this.tab = tabFromHash();
      },
    });
    window.addEventListener("hashchange", () => Alpine.store("nav").setFromHash());
  });

  // ---------------------------------------------------------------------
  // Landing scroll-reveal. One persistent observer is enough: while the
  // home tab is hidden (Alpine x-show -> display:none) the elements have
  // no box and never intersect, so entries only fire when the landing is
  // actually on screen. prefers-reduced-motion is handled in CSS.
  // ---------------------------------------------------------------------
  const revealEls = document.querySelectorAll(".landing .reveal");
  if (revealEls.length && "IntersectionObserver" in window) {
    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    revealEls.forEach((el) => revealObserver.observe(el));
  }

  // ---------------------------------------------------------------------
  // The trailer: a small box over the page on the first visit of a browser
  // session. It starts muted (browsers refuse sound without a click); the
  // "Sound on" chip restarts it with sound. Closing it (the x, Esc, a click
  // outside the box) stops the video and shows the site; it is not shown
  // again until the tab's session ends.
  // ---------------------------------------------------------------------
  const pop = document.getElementById("trailer-pop");
  const video = document.getElementById("trailer-video");
  let seen = false;
  try { seen = sessionStorage.getItem("trailer-seen") === "1"; } catch (_) { /* storage blocked: show it */ }
  if (pop && video && !seen) {
    const sound = document.getElementById("trailer-sound");
    const close = () => {
      video.pause();
      pop.hidden = true;
      document.documentElement.classList.remove("trailer-open");
      try { sessionStorage.setItem("trailer-seen", "1"); } catch (_) { /* fine without */ }
    };
    pop.hidden = false;
    document.documentElement.classList.add("trailer-open");
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) video.play().catch(() => {});
    document.getElementById("trailer-x").addEventListener("click", close);
    pop.addEventListener("click", (e) => { if (e.target === pop) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !pop.hidden) close(); });
    video.addEventListener("ended", close);
    video.addEventListener("volumechange", () => { sound.hidden = !video.muted; });
    sound.addEventListener("click", () => { video.muted = false; video.currentTime = 0; video.play().catch(() => {}); });
  }
})();
