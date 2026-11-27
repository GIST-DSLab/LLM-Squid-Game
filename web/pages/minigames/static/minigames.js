// minigames.html: a card shows its game's description below the cards (one open at a time; the address keeps it: #mines).
(function () {
  const cards = [...document.querySelectorAll(".mg-card")];
  const hint = document.getElementById("mg-hint");

  function show(game) {
    const known = cards.some((c) => c.dataset.game === game);
    cards.forEach((c) => c.setAttribute("aria-expanded", String(c.dataset.game === game)));
    document.querySelectorAll(".mg-detail").forEach((d) => { d.hidden = d.id !== "mg-" + game; });
    hint.hidden = known;
    return known;
  }

  cards.forEach((c) => c.addEventListener("click", () => {
    history.replaceState(null, "", "#" + c.dataset.game);
    show(c.dataset.game);
    document.getElementById("mg-" + c.dataset.game).scrollIntoView({ behavior: "smooth", block: "nearest" });
  }));
  show(location.hash.slice(1));
})();
