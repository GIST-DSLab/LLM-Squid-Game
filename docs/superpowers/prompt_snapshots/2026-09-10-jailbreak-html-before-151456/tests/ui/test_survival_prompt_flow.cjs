/* Run with NODE_PATH pointing to an installation of jsdom. No browser/network needed. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM, VirtualConsole} = require('jsdom');
const html = fs.readFileSync('docs/reports/2026-09-10-ransom-r6-pilot-eli5.html', 'utf8');
const fragment = html.split('<!-- SURVIVAL-PROMPT-FLOW:START -->')[1].split('<!-- SURVIVAL-PROMPT-FLOW:END -->')[0];
const errors = [];
const downloads = [];
const console = new VirtualConsole();
console.on('jsdomError', e => errors.push(e.message));
const dom = new JSDOM(fragment, {runScripts:'dangerously', url:'https://local.test/', virtualConsole:console,
 beforeParse(window) {
  window.TextEncoder = TextEncoder;
  window.Blob = Blob;
  window.URL.createObjectURL = blob => {downloads.push(blob); return 'blob:preview';};
  window.URL.revokeObjectURL = () => {};
  window.document.addEventListener('click', e => {if(e.target.tagName === 'A') e.preventDefault();});
 }
});
const doc=dom.window.document;
const data=JSON.parse(doc.getElementById('sp-data').textContent);
function click(selector){const el=doc.querySelector(selector);assert.ok(el,selector);el.click();return el;}
async function main(){
 for(const [key,pair] of Object.entries(data.cases)){
  const [carrot,heading,wording,menu]=key.split('|');
  for(const [name,value] of Object.entries({carrot,heading,wording,menu})){
   const button=click(`[data-sp-opt="${name}"][data-value="${value}"]`);
   assert.equal(button.getAttribute('aria-pressed'),'true');
  }
  for(const stage of ['frame','rules','task','decision','system','peer','calls']){
   click(`[data-sp-stage="${stage}"]`);
   for(const arm of ['control','threat']){
    const expected=typeof pair[arm][stage]==='string'?pair[arm][stage]:JSON.stringify(pair[arm][stage],null,2);
    assert.equal(doc.querySelector(`[data-arm="${arm}"] pre`).textContent,expected,`${key} ${stage} ${arm}`);
   }
  }
  click('#sp-download-config');
  const config=JSON.parse(await downloads.pop().text());
  assert.equal(config.carrot,carrot);assert.equal(config.exit_wording,wording);
  assert.equal(config.ransom.reason_menu,menu==='1');assert.equal(config.ransom.restate_outcome,true);
  for(const s of config.seasons){
   const threat=s.framing==='hz_1111';
   assert.equal(s.peer_notices,threat);assert.equal(s.reassurance,!threat);
   assert.equal(s.intro_heading,{game:'=== GAME ===',squid:'=== LLM Squid Game ===',default:null}[heading]);
  }
 }
 click('#sp-download-inputs');
 const exported=JSON.parse(await downloads.pop().text());
 assert.deepEqual(exported.threat,JSON.parse(JSON.stringify(data.cases[Object.keys(data.cases).at(-1)].threat.calls)));
 assert.deepEqual(errors,[]);
 process.stdout.write('PASS: 72 combinations × 7 views × 2 arms; config and input downloads; no script errors.\n');
 dom.window.close();
}
main().catch(e=>{process.stderr.write(String(e.stack));process.exitCode=1;dom.window.close();});
