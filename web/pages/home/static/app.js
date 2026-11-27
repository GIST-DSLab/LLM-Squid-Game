// LLM Squid Game — landing page logic.
//
// Pure vanilla JS + Alpine.js (CDN). No build step. The landing never talks
// to a backend: this file keeps only the #home/#about tab store and the
// scroll-reveal observer. (The self-playing rules demo of the old benchmark
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
})();
