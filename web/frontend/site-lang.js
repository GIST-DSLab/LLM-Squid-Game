// Site-wide KO / EN switch (11-20 researcher): a two-button toggle at the right end of every page's top bar.
// It switches only what the site already has in both languages -- the nav labels (English + .nav-ko), and whatever a page
// does on the "site-lang" event (the arena: the language this seat reads; the game log: its prompts). Pages written in
// one language stay as they are; a short note beside the toggle says so. Nothing is translated here.
// A page lists the languages it has in <html data-langs="ko en">; without it, its <html lang>.
(function () {
  const KEY = "site-lang";
  const html = document.documentElement;
  let cur = null;
  try { cur = localStorage.getItem(KEY); } catch (_) { /* storage blocked */ }
  if (cur !== "ko" && cur !== "en") cur = "ko";
  html.dataset.siteLang = cur;

  const css = `
html[data-site-lang="ko"] .nav-en, html[data-site-lang="ko"] .lang-en { display: none !important; }
html[data-site-lang="en"] .nav-ko, html[data-site-lang="en"] .lang-ko { display: none !important; }
html[data-site-lang="ko"] nav.tabs a .nav-ko { margin-left: 0; font-size: inherit; color: inherit; }
.site-lang { display: inline-flex; align-items: center; gap: 8px; margin-left: auto; }
.site-lang-seg { display: inline-flex; border: 1px solid var(--border, #3a3a44); border-radius: 999px; overflow: hidden; }
.site-lang-seg button { all: unset; cursor: pointer; padding: 4px 11px; font: 600 12px/1.2 var(--mono, ui-monospace, monospace);
  letter-spacing: .06em; color: var(--text-dim, #9a9aa6); }
.site-lang-seg button[aria-pressed="true"] { background: var(--accent, #e6007e); color: #fff; }
.site-lang-seg button:focus-visible { outline: 2px solid var(--accent, #e6007e); outline-offset: -2px; }
.site-lang-note { font-size: 11.5px; color: var(--text-dim, #9a9aa6); white-space: nowrap; }
@media (max-width: 640px) { .site-lang-note { display: none; } }`;

  function langsOfPage() {
    return (html.dataset.langs || html.getAttribute("lang") || "ko").split(/[\s,]+/).filter(Boolean);
  }
  // nav links read "English <span class=nav-ko>한국어</span>": wrap the English text so either side can be hidden
  function wrapNav() {
    document.querySelectorAll("nav.tabs a").forEach((a) => {
      if (!a.querySelector(".nav-ko") || a.querySelector(".nav-en")) return;
      [...a.childNodes].forEach((n) => {
        if (n.nodeType === 3 && n.textContent.trim()) {
          const s = document.createElement("span");
          s.className = "nav-en";
          s.textContent = n.textContent.trim();
          n.replaceWith(s, document.createTextNode(" "));
        }
      });
    });
  }
  function paint() {
    document.querySelectorAll(".site-lang-seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.l === cur)));
    const note = document.querySelector(".site-lang-note");
    if (note) {
      const has = langsOfPage();
      note.textContent = has.includes(cur) ? "" : cur === "en" ? "This page is in Korean only for now" : "이 페이지는 아직 영어판만 있습니다";
    }
  }
  function set(l) {
    if ((l !== "ko" && l !== "en") || l === cur) return;
    cur = l;
    html.dataset.siteLang = l;
    try { localStorage.setItem(KEY, l); } catch (_) { /* storage blocked */ }
    paint();
    window.dispatchEvent(new CustomEvent("site-lang", { detail: l }));
  }
  function mount() {
    const st = document.createElement("style");
    st.textContent = css;
    document.head.appendChild(st);
    wrapNav();
    const bar = document.querySelector("header.topbar");
    if (bar && !bar.querySelector(".site-lang")) {
      const box = document.createElement("div");
      box.className = "site-lang";
      box.innerHTML = '<span class="site-lang-note" aria-live="polite"></span>' +
        '<span class="site-lang-seg" role="group" aria-label="Language / 언어">' +
        '<button type="button" data-l="ko" title="한국어">KO</button><button type="button" data-l="en" title="English">EN</button></span>';
      box.addEventListener("click", (ev) => { const b = ev.target.closest("button[data-l]"); if (b) set(b.dataset.l); });
      bar.appendChild(box);
    }
    paint();
  }
  window.siteLang = { get: () => cur, set };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();

// Links to a page that can come and go (web/pages/<page>/static, e.g. probe.html) carry data-optional:
// when the page is not there (its folder was deleted), the link is hidden.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("a[data-optional]").forEach(function (a) {
    fetch(a.getAttribute("href"), { method: "HEAD" })
      .then(function (r) { if (!r.ok) a.style.display = "none"; })  // not .hidden: .btn sets its own display
      .catch(function () { /* offline or file://: leave the link */ });
  });
});
