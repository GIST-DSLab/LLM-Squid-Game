// The squid5 engine under Pyodide in Node: the CI guard for the browser arena (web/pyodide/tests/test_pyodide_node.py).
//
//   npm ci --prefix web/pyodide && python web/pyodide/build_bundle.py && node web/pyodide/node_check.mjs [--rounds 8]
//
// Loads the same Pyodide as the page (package.json pins it; pyyaml comes from the Pyodide CDN), unpacks the engine
// bundle that build_bundle.py made (web/frontend/engine/manifest.json), and runs selfcheck.py: one full game of
// 1 person + 3 bots through browser.Arena, then the signal page. Prints one JSON line with the timings and the event
// digest (the pytest wrapper compares it with CPython's).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPyodide } from "pyodide";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const arg = (name, dflt) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : dflt; };
const engineDir = arg("--engine", join(repo, "web", "frontend", "engine"));
const rounds = Number(arg("--rounds", "8"));

const t0 = performance.now();
const py = await loadPyodide();
const tLoad = performance.now();
await py.loadPackage("pyyaml", { messageCallback: () => {} });
const tPkg = performance.now();
const man = JSON.parse(readFileSync(join(engineDir, "manifest.json"), "utf8"));
py.unpackArchive(new Uint8Array(readFileSync(join(engineDir, man.file))), "zip", { extractDir: "/home/pyodide/squid5" });
py.FS.writeFile("/home/pyodide/squid5/selfcheck.py", readFileSync(join(here, "selfcheck.py"), "utf8"));
await py.runPythonAsync(`import sys; sys.path.insert(0, "/home/pyodide/squid5")`);
const tImp0 = performance.now();
await py.runPythonAsync("import browser, selfcheck");
const tImport = performance.now();
const out = JSON.parse(await py.runPythonAsync(`import json; json.dumps(await selfcheck.run(${rounds}))`));
const tEnd = performance.now();
out.bundle = man.bundle;
out.pyodide = py.version;
out.python = py.runPython("import sys; sys.version.split()[0]");
out.timings_s = {
  pyodide_load: +((tLoad - t0) / 1000).toFixed(3), pyyaml: +((tPkg - tLoad) / 1000).toFixed(3),
  engine_import: +((tImport - tImp0) / 1000).toFixed(3), checks: +((tEnd - tImport) / 1000).toFixed(3),
  total: +((tEnd - t0) / 1000).toFixed(3),
};
console.log(JSON.stringify(out));
