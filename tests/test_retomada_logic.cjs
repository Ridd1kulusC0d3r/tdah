/* Exercises the actual inline application functions without requiring Chromium.
   This is state/handler coverage, not a replacement for test_retomada_ui.py. */
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('app/index.html', 'utf8');
function fn(name) {
  const start = source.indexOf('function ' + name + '(');
  assert(start >= 0, name);
  const end = source.indexOf('\nfunction ', start + 1);
  return source.slice(start, end < 0 ? source.indexOf('</script>', start) : end);
}
const nodes = new Map();
const node = key => { if (!nodes.has(key)) nodes.set(key, {value:'', dataset:{}, setAttribute(){}});return nodes.get(key); };
const buttons = ['feita', 'avancei', 'retomar'].map(fim=>({dataset:{fim}}));
let latestHtml = '';
const ctx = {console, Date, setTimeout(){}, clearTimeout(){}, URL, Blob, document:{title:''},
  navigator:{}, S:{}, FOCO:null, AUD:null, API:null,
  $: sel=>node(sel), $$: sel=>sel==='[data-fim]'?buttons:[],
  som(){}, salaSair(){}, NATIVO:()=>null, save(){}, fechar(){}, toast(){},
  sheet(html, cb){latestHtml=html; if(cb)cb({});},
  esc:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
  hoje:()=> '2026-11-22', diasAtras:n=>new Date(Date.UTC(2026,10,22-n)).toISOString().slice(0,10),
  fmtData:s=>s, soma:xs=>xs.reduce((a,b)=>a+b,0), media:xs=>xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:0, r1:n=>Math.round(n*10)/10
};
vm.createContext(ctx);
const names=['curso','itemPorId','tarefa','alvo','aulaFeita','concluir','snapshot','cartaoRetomada','prep','textoPreparo','textoPreparoFinal','terminarFoco','sheetMenor'];
// Select functions with following section-level declarations trimmed when present.
for (const n of names) vm.runInContext(fn(n).split('\n/* =================')[0],ctx);
const run=s=>vm.runInContext(s,ctx);
const reset=()=>{nodes.clear();run(`S={profile:{name:'Teste'},tasks:[{id:'t',title:'Tarefa',type:'estudo',steps:[],done:false}],courses:[{id:'c',name:'Curso',done:2,total:8}],sessions:[],checkins:{},routineRuns:[],settings:{focusMin:25}};`);};
const finish=(id, choice, small=false)=>{run(`FOCO={taskId:${JSON.stringify(id)},type:'estudo',curso:${id.startsWith('c:')},total:120,end:Date.now(),pequeno:${small?"{texto:'Abrir livro',min:2}":'null'}};terminarFoco(true,true);`);node('#fProx').value='Próximo passo';node('#fAvanco').value='Li a página 12';node('#fMaterial').value='apostila.pdf';buttons.find(b=>b.dataset.fim===choice).onclick();};
reset();finish('t','avancei');assert.equal(run('S.tasks[0].done'),false);assert.equal(run('S.tasks[0].parou.material'),'apostila.pdf');assert.equal(run('S.sessions[0].min'),2);
finish('t','avancei');assert.equal(run('S.tasks[0].steps.length'),0,'no duplicated subtasks');
run('concluir(S.tasks[0])');assert.equal(run('S.tasks[0].parou'),undefined);
reset();finish('c:c','avancei');assert.equal(run("itemPorId('c:c').parou.prox"),'Próximo passo');assert(run('textoPreparo()').includes('Curso (próximo passo: Próximo passo)'),'numeric course progress must not hide resumption');run('aulaFeita(S.courses[0])');assert.equal(run('S.courses[0].done'),3);assert.equal(run('S.courses[0].parou'),undefined);
reset();finish('t','feita',true);assert.equal(run('S.tasks[0].done'),false);assert.equal(run('S.sessions[0].fim'),'passo');assert.equal(run('S.settings.focusMin'),25);
reset();finish('c:c','feita',true);assert.equal(run('S.courses[0].done'),2);
run("prep().atrapalhou='private';prep().editado='Only this text';");assert.equal(run('textoPreparoFinal()'),'Only this text');assert.equal(run("'preparo' in snapshot()"),false);assert.equal(run('prep().incl.bem'),false);
run("S.tasks[0].parou={em:hoje(),prox:'<img onerror=alert(1)>',material:'javascript:alert(1)'}");const html=run('cartaoRetomada(S.tasks[0])');assert(!html.includes('<img'));assert(!html.includes('href='));assert(html.includes('&lt;img'));
reset();run("sheetMenor('t')");assert(latestHtml.includes('Hoje cabe menos'));node('#smPasso').value='';node('#smMin').value='2';node('#smIniciar').onclick();assert.equal(run('FOCO'),null);
ctx.abrirFoco=(id,small)=>{assert.equal(id,'t');assert.equal(small.min,2);assert.equal(small.texto,'Abrir livro')};node('#smPasso').value='Abrir livro';node('#smIniciar').onclick();
console.log('PASS: task/course resumption, partial progress, reduced steps, source preservation, summary selection/export text, private snapshot, escaping and empty-step validation.');
