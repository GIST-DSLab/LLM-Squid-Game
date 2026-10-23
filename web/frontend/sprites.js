// The seat characters and the SOLVER ticket, copied from the game-log viewer (tools/monitor/static/monitor.js, 10-16 /
// 10-17: our own pixel art as inline SVG, no image files) so the arena shows the same four players. Seat k % 4 ->
// player 456 / 001 / 218 / 067, seat colour var(--a0..3). window.SQUID = {avatar(k, h), lot(h), num(k)}.
(function () {
  "use strict";
  const SQ_W = 24, SQ_H = 32;
  const SQ_DIG = { 0: ["111", "101", "101", "101", "111"], 1: ["010", "110", "010", "010", "111"], 2: ["111", "001", "111", "100", "111"], 3: ["111", "001", "111", "001", "111"],
    4: ["101", "101", "111", "001", "001"], 5: ["111", "100", "111", "001", "111"], 6: ["111", "100", "111", "101", "111"], 7: ["111", "001", "010", "010", "010"],
    8: ["111", "101", "111", "101", "111"], 9: ["111", "101", "111", "001", "111"] };
  // heads: 13 px wide at x 6..18 from row 1 (hair rows, then the face); '.' = nothing
  const SQ = [
    { num: "456", hair: "#2b221c", brow: "#2b221c", tee: true, rows: [ // messy medium dark hair, unshaven, white tee under the jacket
      "..H..HH.H.H..", ".HHHHHHHHHHH.", "HHHHHHHHHHHHH", "HHHHHHHHHHHHH", "HHHSSHHHSSHHH",
      "HSBBBSSSBBBSH", "HSSSSSSSSSSSH", "SSWESSSSSWESS", "SSEESSSSSEESS", "sSSSSSnSSSSSs", ".SUUSMMMSUUS.", "..SUUUUUUUS.."] },
    { num: "001", hair: "#dcd9d2", brow: "#b9b4ab", hunch: true, rows: [ // old man: thin grey hair, wrinkles, head forward and down
      ".............", "....HHHHH....", "..HSSSSSSSH..", ".HSSSSSSSSSH.", "HHSwwSwwSwwHH",
      "HSBBBSSSBBBSH", "HSSSSSSSSSSSH", "SwWESSSSSWEwS", "SSEESSSSSEESS", "sSSSSSnSSSSSs", ".SSwSMMMSwSS.", "..SSSSSSSSS.."] },
    { num: "218", hair: "#121216", brow: "#121216", rows: [ // neat short black side-parted hair, serious brows
      ".............", "..HHHHHHHHH..", ".HHHHHHHHHHH.", "HHHHSHHHHHHHH", "HHHSSSSHHHHHH",
      "HBBBSSSSSBBBH", "SSSBSSSSSBSSS", "SSWESSSSSWESS", "SSEESSSSSEESS", "sSSSSSnSSSSSs", ".SSSSMMMSSSS.", "..SSSSSSSSS.."] },
    { num: "067", hair: "#1d1616", brow: "#1d1616", long: true, rows: [ // dark hair framing the face, down to the shoulders
      ".............", "..HHHHHHHHH..", ".HHHHHHHHHHH.", "HHHHHHHHHHHHH", "HHHHHHHHHHHHH",
      "HHSSSSSSSSSHH", "HSBBSSSSSBBSH", "HSWESSSSSWESH", "HSEESSSSSEESH", "HSSSSSnSSSSSH", "HSSSSMMMSSSSH", "HHSSSSSSSSSHH"] },
  ];
  const SQ_COL = { S: "#f1c7a1", s: "#d9a77f", n: "#cf966f", E: "#1a1a1a", M: "#a5534c", U: "#b89784", w: "#c79676", G: "#24876f", g: "#17604f",
    L: "#e6f1ed", T: "#f4f4f2", W: "#fbfbf8", N: "#151515", P: "#1f7a64", k: "#22252b" };
  const sqGrids = [];
  function sqGrid(k) { // {body, legs0, legs1}: rows of SQ_W chars ('.' = empty)
    k %= 4;
    if (sqGrids[k]) return sqGrids[k];
    const mk = () => Array.from({ length: SQ_H }, () => Array(SQ_W).fill("."));
    const g = mk(), C = SQ[k];
    const rect = (G, x0, y0, x1, y1, c) => { for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) G[y][x] = c; };
    rect(g, 10, 13, 14, 13, "s"); // neck
    rect(g, 5, 14, 19, 14, "G"); rect(g, 4, 15, 20, 15, "G"); rect(g, 3, 16, 21, 25, "G"); // jacket
    rect(g, 3, 16, 3, 25, "g"); rect(g, 21, 16, 21, 25, "g"); rect(g, 4, 16, 4, 25, "L"); rect(g, 20, 16, 20, 25, "L"); rect(g, 3, 25, 21, 25, "g");
    if (C.tee) rect(g, 10, 14, 14, 15, "T"); else rect(g, 10, 14, 14, 14, "g");
    g[26][3] = "S"; g[26][21] = "S"; // hands
    rect(g, 6, 16, 18, 22, "W"); // the number patch
    [...C.num].forEach((d, n) => SQ_DIG[d].forEach((row, y) => [...row].forEach((b, x) => { if (b === "1") g[17 + y][7 + n * 4 + x] = "N"; })));
    const dx = C.hunch ? 1 : 0, dy = C.hunch ? 1 : 0;
    C.rows.forEach((row, y) => [...row].forEach((c, x) => { if (c !== ".") g[1 + y + dy][6 + x + dx] = c; }));
    if (C.long) { rect(g, 6, 13, 7, 15, "H"); rect(g, 17, 13, 18, 15, "H"); }
    const l0 = mk(), l1 = mk(); // legs: standing / one step
    rect(l0, 7, 26, 17, 26, "P"); rect(l0, 7, 27, 11, 29, "P"); rect(l0, 13, 27, 17, 29, "P"); rect(l0, 6, 30, 11, 30, "K"); rect(l0, 13, 30, 18, 30, "K"); rect(l0, 6, 31, 11, 31, "k"); rect(l0, 13, 31, 18, 31, "k");
    rect(l1, 7, 26, 17, 26, "P"); rect(l1, 7, 27, 11, 28, "P"); rect(l1, 13, 27, 17, 29, "P"); rect(l1, 6, 29, 11, 29, "K"); rect(l1, 6, 30, 11, 30, "k"); rect(l1, 13, 30, 18, 30, "K"); rect(l1, 13, 31, 18, 31, "k");
    const ring = (L) => { // the empty pixels next to the figure (body + these legs), in the seat colour
      const o = mk(), full = (x, y) => x >= 0 && y >= 0 && x < SQ_W && y < SQ_H && (g[y][x] !== "." || L[y][x] !== ".");
      for (let y = 0; y < SQ_H; y++) for (let x = 0; x < SQ_W; x++)
        if (!full(x, y) && (full(x - 1, y) || full(x + 1, y) || full(x, y - 1) || full(x, y + 1))) o[y][x] = "O";
      return o;
    };
    return (sqGrids[k] = { body: g, legs0: l0, legs1: l1, ring0: ring(l0), ring1: ring(l1) });
  }
  function sqRects(G, k, y0, y1) { // horizontal runs of one colour -> one rect each
    const col = Object.assign({}, SQ_COL, { H: SQ[k % 4].hair, B: SQ[k % 4].brow, K: "var(--a" + (k % 4) + ")", O: "var(--a" + (k % 4) + ")" });
    let out = "";
    for (let y = y0; y <= y1; y++) for (let x = 0; x < SQ_W; ) {
      const c = G[y][x]; let e = x + 1;
      while (e < SQ_W && G[y][e] === c) e++;
      if (col[c]) out += '<rect x="' + x + '" y="' + y + '" width="' + (e - x + 0.02) + '" height="1.02" fill="' + col[c] + '"/>';
      x = e;
    }
    return out;
  }
  // the whole character (stage), legs in two frames; ``title`` = the player number
  function squidAvatar(k, h) {
    const q = sqGrid(k);
    return '<svg class="pix sq" viewBox="0 0 ' + SQ_W + " " + SQ_H + '" width="' + Math.round((h * SQ_W) / SQ_H) + '" height="' + h + '" shape-rendering="crispEdges" role="img" aria-label="' + SQ[k % 4].num + '">' +
      '<g class="f0">' + sqRects(q.ring0, k, 0, SQ_H - 1) + sqRects(q.legs0, k, 26, SQ_H - 1) + '</g><g class="f1">' + sqRects(q.ring1, k, 0, SQ_H - 1) + sqRects(q.legs1, k, 26, SQ_H - 1) + "</g>" +
      sqRects(q.body, k, 0, SQ_H - 1) + "</svg>";
  }
  // head and shoulders with the number patch, on the seat colour (profile icons: messenger, step records, graph)
  const LOT = [".KKKKKKKKKK.", "KKKKKKKKKKKK", "KKRRKKKKRRKK", "KKKRRKKRRKKK", ".KKKRRRRKKK.", "KKKRRKKRRKKK", "KKRRKKKKRRKK", "KKKKKKKKKKKK", ".KKKKKKKKKK."];
  const pixRuns = (rows, col, dx, dy) => { // horizontal runs of one colour -> one rect each ('.' or unknown = nothing)
    let out = "";
    rows.forEach((row, y) => { for (let x = 0; x < row.length; ) { const c = row[x]; let e = x + 1; while (e < row.length && row[e] === c) e++;
      if (col[c]) out += '<rect x="' + (x + dx) + '" y="' + (y + dy) + '" width="' + (e - x + 0.02) + '" height="1.02" fill="' + col[c] + '"/>'; x = e; } });
    return out;
  };
  const ringOf = (rows) => rows.map((row, y) => [...row].map((c, x) => { // the empty pixels next to the figure
    const full = (i, j) => j >= 0 && j < rows.length && i >= 0 && i < rows[j].length && rows[j][i] !== ".";
    return c === "." && (full(x - 1, y) || full(x + 1, y) || full(x, y - 1) || full(x, y + 1)) ? "O" : ".";
  }).join(""));
  let lotSvg = "";
  function lotIcon(h) {
    if (!lotSvg) { const padded = [" ".repeat(14)].concat(LOT.map((r) => "." + r + "."), [".".repeat(14)]).map((r) => r.replace(/ /g, "."));
      lotSvg = pixRuns(ringOf(padded), { O: "#f4f1ea" }, 0, 0) + pixRuns(padded, { K: "#141414", R: "#e3342b" }, 0, 0); }
    return '<svg class="pix lot" viewBox="0 0 14 11" width="' + Math.round((h * 14) / 11) + '" height="' + h + '" shape-rendering="crispEdges" role="img" aria-label="SOLVER">' + lotSvg + "</svg>";
  }
  window.SQUID = { avatar: squidAvatar, lot: lotIcon, num: (k) => SQ[k % 4].num };
})();
