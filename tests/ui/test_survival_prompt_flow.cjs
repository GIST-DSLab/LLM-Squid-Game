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
 assert.equal(Object.keys(data.jailbreak).length,10);
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
  for(const [id,item] of Object.entries(data.jailbreak)){
   const button=click(`[data-sp-opt="jailbreak"][data-value="${id}"]`);
   assert.equal(button.getAttribute('aria-pressed'),'true');
   assert.equal(doc.getElementById('sp-download-config').disabled,id!=='off');
   assert.equal(doc.getElementById('sp-jailbreak-reference').textContent,item.reference_text||'선택한 추가 문구가 없습니다.');
   for(const stage of ['frame','rules','task','decision','system','peer','calls','jailbreak']){
    click(`[data-sp-stage="${stage}"]`);
    for(const arm of ['control','threat']){
     const original=pair[arm];
     const displayed=doc.querySelector(`[data-arm="${arm}"] pre`).textContent;
     let expected=original[stage];
     if(stage==='jailbreak')expected=item.text||'추가 문구 없음';
     else if((stage==='system'||stage==='frame')&&item.placement==='system_head')expected=item.text+'\n\n'+expected;
     else if(stage==='system'&&item.placement==='system_tail')expected+='\n\n'+item.text;
     if(stage==='calls'){
      const calls=JSON.parse(displayed);
      for(const name of ['task','decision']){
       assert.deepEqual(calls[name][1],original.calls[name][1]);
       const system=calls[name][0];
       assert.equal(system.role,'system');
       if(item.placement==='system_head')assert.equal(system.content,item.text+'\n\n'+original.system);
       else if(item.placement==='system_tail')assert.equal(system.content,original.system+'\n\n'+item.text);
       else assert.equal(system.content,original.system);
      }
     }else assert.equal(displayed,expected,`${key} ${id} ${stage} ${arm}`);
    }
   }
   click('#sp-download-inputs');
   const preview=JSON.parse(await downloads.pop().text());
   assert.equal(preview.options.jailbreak,id);assert.equal(preview.preview_only,id!=='off');
   assert.deepEqual(preview.jailbreak,item);
   click('[data-sp-stage="calls"]');
   for(const arm of ['control','threat'])assert.deepEqual(preview[arm],JSON.parse(doc.querySelector(`[data-arm="${arm}"] pre`).textContent));
  }
  click('[data-sp-opt="jailbreak"][data-value="off"]');
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
 process.stdout.write('PASS: 72 combinations × 10 jailbreak choices × 8 views × 2 arms; attachment roles and exports; no script errors.\n');
 dom.window.close();
}
main().catch(e=>{process.stderr.write(String(e.stack));process.exitCode=1;dom.window.close();});
