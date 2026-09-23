'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let token=location.hash.slice(1)||sessionStorage.getItem('tcs-session-token');
if(token){sessionStorage.setItem('tcs-session-token',token);history.replaceState(null,'',location.pathname);}
let app=null,plan=null,gameInfo=null,dirty=true,pendingModule=null,conflictPage=0;
const decisions={};
function error(e){$('toastText').textContent=e.message||String(e);$('toast').hidden=false;}
async function api(path,data,method='POST'){
 const response=await fetch('/api/'+path,{method,headers:{'X-TCS-Token':token||'','Content-Type':'application/json'},...(method==='GET'?{}:{body:JSON.stringify(data||{})})});
 const result=await response.json();if(!response.ok)throw new Error(result.error||response.statusText);return result;
}
const stageToStep={prepare:1,downloads:2,mapping:3,compare:4,install:5,verify:5,launch:5};
const stepNames=['','Spiel auswählen','Downloads','Archive zuordnen','Zusammenführen','Installieren','Weitergeben'];
function nextStepNumber(){
 if(plan&&!dirty&&!plan.counts.conflicts)return 5;
 const pending=app?.steps?.stages?.find(stage=>stage.status!=='done');
 return pending?stageToStep[pending.id]||1:5;
}
function updateNextStep(){
 const n=nextStepNumber(),button=$('resumeStepBtn');
 button.dataset.step=String(n);
 button.textContent=`Zu Schritt ${n}: ${stepNames[n]} →`;
}
function step(n){
 if($('progress').classList.contains('done'))$('progress').hidden=true;
 const target=$('step'+n);
 document.querySelectorAll('.step').forEach(e=>e.classList.toggle('active',e===target));
 document.querySelectorAll('.nav').forEach(e=>{
  const active=e.dataset.step===String(n);
  e.classList.toggle('active',active);
  if(active)e.setAttribute('aria-current','step');else e.removeAttribute('aria-current');
 });
 target.scrollIntoView({block:'start',behavior:'auto'});
 if(n===5)updateGates();
}
function markDirty(resetReview=false){if(resetReview){for(const k of Object.keys(decisions))delete decisions[k];}dirty=true;$('planFreshness').textContent='Auswahl geändert. Bitte erneut vergleichen.';updateGates();}
function sourceById(id){return app?.state.sources.find(s=>s.id===id);}
function suggested(roots,mode){if(roots.length===1)return [...roots];const classic=roots.filter(r=>r.toLowerCase().includes('classic'));let common=roots.filter(r=>!/(optional|film.?accurate|e3.?2019|vader|icon|classic)/i.test(r));if(common.length){let d=Math.min(...common.map(r=>r?r.split('/').length:0));common=common.filter(r=>(r?r.split('/').length:0)===d);}return mode==='classic'?[...common,...classic.slice(0,1)]:common.length===1?common:[];}
function settings(){return {game:$('gamePath').value.trim(),baseline:$('baselinePath').value.trim(),selections:app.state.selections,decisions:{},options:{clean_target_confirmed:$('cleanTarget').checked,prepared_confirmed:$('prepared').checked,baseline_confirmed:$('baselineConfirmed').checked,graphics:$('graphics').checked}};}
async function loadState(fill=false,background=false){
 const next=await api('state',null,'GET');
 // Background refresh must not erase a user's unsaved confirmations or choices.
 const before=app?JSON.stringify([app.state.sources,app.state.selections]):'';
 if(background&&app){
  for(const [mid,choice] of Object.entries(app.state.selections)){
   if(next.state.selections[mid]?.source_id===choice.source_id)next.state.selections[mid]={...choice,roots:[...choice.roots]};
  }
 }
 app=next;
 if(typeof recordObservedState==='function')recordObservedState(app);
 $('runtimeBadge').textContent='● Lokal verbunden · Python '+app.python_version;
 if(fill&&!background){$('gamePath').value=app.state.game||'';$('baselinePath').value=app.state.baseline||'';const o=app.state.options||{};for(const [id,key]of [['cleanTarget','clean_target_confirmed'],['prepared','prepared_confirmed'],['baselineConfirmed','baseline_confirmed'],['graphics','graphics']])$(id).checked=!!o[key];}
 if(!background||before!==JSON.stringify([app.state.sources,app.state.selections])){renderDownloads();renderModules();}
 updateGates();updateNextStep();if(typeof renderJourney==='function')renderJourney(app.steps);if(typeof renderReadiness==='function')renderReadiness();if(typeof renderJob==='function')renderJob(app.job);
}
function renderDownloads(){
 $('downloadCards').innerHTML=app.profile.modules.map((m,i)=>{const s=app.state.selections[m.id];const ready=s?.source_id;const selected=s?.enabled??m.default_enabled;return `<article class="panel download-card ${selected?'':'optional-muted'}"><div class="row spaced"><span class="cardnum">0${i+1}</span><span class="pill ${ready?'good':''}">${ready?'Archiv hinzugefügt':m.default_enabled===false?'Optional · standardmäßig aus':'Download beim Autor'}</span></div><h2>${esc(m.name)}</h2><small>${esc(m.author)}</small><span class="filename">${esc(m.file)}</span><p class="muted">${esc(m.description)}</p><div class="destination"><strong>Ziel:</strong> ${esc(m.destination)}</div><div class="cardactions"><button class="primary small" data-open-module="${m.id}">Richtige Datei öffnen ↗</button><button class="small" data-upload-module="${m.id}">Archiv hinzufügen</button><button class="small" data-nexus-module="${m.id}">Über Nexus laden</button></div></article>`;}).join('');
 $('toolCards').innerHTML=app.profile.tools.map(t=>`<div class="listline"><div><strong>${esc(t.name)}</strong><br><small>${esc(t.required)}</small></div><div style="flex:1;max-width:600px"><strong>${esc(t.file)}</strong><p class="muted" style="margin:7px 0">${esc(t.destination)}</p><a href="${esc(t.url)}" target="_blank" rel="noopener noreferrer">Offizielle Seite öffnen ↗</a>${t.id==='sevenzip'?`<br><small>${app.sevenzip?'7-Zip wurde erkannt.':'7-Zip ist noch nicht erkannt. ZIPs funktionieren bereits.'}</small>`:''}</div></div>`).join('');
 $('archiveStatus').textContent=app.state.sources.length+' lokale Quelle(n) erkannt';
}
function renderModules(){
 $('moduleCards').innerHTML=app.profile.modules.map((m,i)=>{
  let sel=app.state.selections[m.id];if(!sel){sel={enabled:m.default_enabled!==false,confirmed:false,roots:[],source_id:''};app.state.selections[m.id]=sel;}
  const source=sourceById(sel.source_id);const roots=source?.roots||[];
  return `<article class="panel" data-module="${m.id}"><div class="module-heading"><div><small>REIHENFOLGE ${i+1}</small><h2>${esc(m.name)}</h2></div><label class="check" style="margin:0"><input type="checkbox" data-enabled="${m.id}" ${sel.enabled?'checked':''}>Aktiv</label></div><label><small>Passendes Archiv oder entpackter Ordner</small><select data-source="${m.id}"><option value="">Bitte Quelle wählen …</option>${app.state.sources.map(s=>`<option value="${s.id}" ${sel.source_id===s.id?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label><div class="rootlist">${roots.length?roots.map(r=>`<label class="check ${sel.roots.includes(r)?'selected':''}"><input type="checkbox" data-root-module="${m.id}" data-root="${esc(r)}" ${sel.roots.includes(r)?'checked':''}><span><strong>${esc(r||'(direkte CHARS/STUFF/LEVELS-Ordner)')}</strong><br><small>${source.root_counts[r]||0} Datendateien · nur dieser Teil, keine alternativen Unterpakete</small></span></label>`).join(''):'<div class="empty">Erst das passende Archiv in Schritt 2 hinzufügen.</div>'}</div>${source?`<div class="row spaced" style="margin-top:12px"><small>Archiv-Hash ${esc(source.archive_sha256?.slice(0,16)||'Ordnerquelle')} · nicht mit Autorenhash verifiziert</small><button class="small" data-suggest="${m.id}">Ordner vorschlagen</button></div>`:''}<label class="check"><input type="checkbox" data-confirm="${m.id}" ${sel.confirmed?'checked':''}><span><strong>Datei, Variante und Unterordner sind richtig.</strong><br><small>${esc(m.file)}${m.root_mode==='classic'?' · gemeinsame Dateien + Classic-Icons':''}</small></span></label></article>`;
 }).join('');
}
function installedSummary(){
 const readiness=app?.state.readiness;
 if(readiness?.user_reported_game_test)return {headline:'Spieltest bestätigt.',message:'Du hast Spielstart und Modfunktion im Spiel bestätigt.'};
 if(readiness?.can_launch)return {headline:'Mods installiert · jetzt im Spiel testen.',message:'Installierte Dateien geprüft. Der Spieltest steht noch aus.'};
 return {headline:'Mods installiert · Dateien erneut prüfen.',message:'Die letzte Dateiprüfung ist nicht gültig. Installation erneut prüfen, bevor du das Spiel startest.'};
}
function renderPlan(){
 if(!plan)return;const c=plan.counts;
 $('metrics').innerHTML=[['Dateien',c.files],['Automatische Überlagerungen',c.recipe_overlays||0],['Automatische Text-Merges',c.text_merges||0],['Offene Konflikte',c.conflicts]].map(([label,value])=>`<div class="metric"><strong>${value.toLocaleString('de-DE')}</strong><span>${label}</span></div>`).join('');
 $('downloadReportBtn').disabled=false;$('conflictTools').hidden=!c.conflicts;
 $('planFreshness').textContent=dirty?'Auswahl geändert. Erneut vergleichen.':c.conflicts?'Unbekannte Kollisionen bleiben gesperrt.':'Bekannte Überschneidungen automatisch geregelt · Spieltest offen';
 if(!dirty&&!c.conflicts&&!app?.state.installed_game){$('autoHeadline').textContent='Dateiplan bereit · als Nächstes installieren';$('autoMessage').textContent='Bekannte Dateikollisionen automatisch geregelt. Installation und Spieltest stehen noch aus.';}
 renderConflicts();updateGates();
}
function renderConflicts(){
 if(!plan)return;const filter=$('conflictFilter').value.toLowerCase();const items=plan.conflicts.filter(r=>r.path.toLowerCase().includes(filter));const pages=Math.max(1,Math.ceil(items.length/30));conflictPage=Math.min(conflictPage,pages-1);const page=items.slice(conflictPage*30,(conflictPage+1)*30);
 $('conflicts').innerHTML=page.length?page.map(r=>`<article class="conflict"><span class="path">${esc(r.path)}</span><span class="pill bad">Automatik angehalten</span><p class="desc" style="margin:10px 0 0">${esc(r.reason)}</p><div class="row"><button class="small" data-preview="${esc(r.key)}">Unterschied ansehen</button></div></article>`).join(''):`<div class="notice good">${plan.counts.conflicts?'Keine Treffer für diesen Filter.':'Keine ungelösten Dateikonflikte. Der Build kann erstellt werden. Das ist keine In-Game-Kompatibilitätsfreigabe.'}</div>`;
 $('conflictPaging').innerHTML=items.length>30?`<button class="small" id="prevPage" ${conflictPage===0?'disabled':''}>←</button><small>Seite ${conflictPage+1} / ${pages} · ${items.length} Konflikte</small><button class="small" id="nextPage" ${conflictPage>=pages-1?'disabled':''}>→</button>`:'';
}
function updateGates(){const ready=!!plan&&!dirty&&plan.counts.conflicts===0;const installed=!!app?.state.installed_game;$('toInstallBtn').disabled=!ready;$('buildBtn').disabled=!ready;const direct=ready&&app?.platform==='nt'&&$('cleanTarget').checked&&$('prepared').checked;
 $('installBtn').disabled=!direct||installed;$('launchBtn').disabled=!installed;
 $('installGate').textContent=installed?(app.state.readiness?.can_launch?'Moddateien installiert und geprüft. Jetzt den Spielstart testen oder bei Bedarf die Sicherung wiederherstellen.':'Moddateien installiert. Vor dem Spielstart die Installation erneut prüfen.'):!ready?'Für diesen Stand fehlt ein aufgelöster, aktueller Prüfbericht. In Schritt 4 erneut vergleichen.':direct?'Dateiplan bereit. Die vorbereitete Spielkopie wird vor dem Kopieren gesichert.':'Mod-ZIP kann gebaut werden. Für Direktinstallation zusätzlich Windows und die bestätigten Voraussetzungen aus Schritt 1 nötig.';
 $('installGate').className='notice'+((installed?!!app.state.readiness?.can_launch:ready)?' good':'');
 if(installed){const summary=installedSummary();$('autoHeadline').textContent=summary.headline;$('autoMessage').textContent=summary.message;}}
async function busyJob(start,title){
 $('progress').hidden=true;$('progress').classList.remove('done');$('hideProgressBtn').hidden=true;$('progressTitle').textContent=title;$('progressLog').textContent='';document.body.classList.add('busy');
 try{
  await start();let job;
  do{await sleep(400);job=await api('job',null,'GET');$('progressLog').textContent=(job.logs||[]).slice(-4).join('\n');$('progressPhase').textContent=job.phase_label||title;renderJob(job);}while(job.running);
  if(typeof recordObservedJob==='function')recordObservedJob(job);
  if(job.error)throw new Error(job.error);$('progressTitle').textContent='Arbeitsschritt abgeschlossen';return job.result;
 }finally{document.body.classList.remove('busy');$('progress').classList.add('done');$('hideProgressBtn').hidden=false;$('progress').hidden=true;}
}
async function selectFolder(inputId){const result=await api('picker',{kind:'folder'});if(result.path){$(inputId).value=result.path;markDirty();}}
async function checkGame(){
 $('toast').hidden=true;gameInfo=null;$('gameStatus').innerHTML='<div class="notice">Ordner wird geprüft …</div>';
 try{const value=$('gamePath').value.trim().replace(/^"|"$/g,'');gameInfo=await api('game',{path:value});$('gamePath').value=gameInfo.path;
 const ready=gameInfo.prepared_structure&&!gameInfo.active_data_archives?.length;
 $('gameStatus').innerHTML=`<div class="notice ${ready?'good':''}"><strong>${ready?'Lose Spieldaten vorhanden':'Spielvorbereitung kann automatisch gestartet werden'}</strong><br>${esc(gameInfo.note)}${gameInfo.active_install?'<br><strong>Vor neuer Installation den bestehenden Modbuild wiederherstellen.</strong>':''}${gameInfo.preparation_backup?'<br>Original-DAT-Backup vorhanden.':''}</div><small>EXE gefunden · SHA-256 ${esc(gameInfo.exe_sha256.slice(0,20))}… · kein offizieller Hashabgleich, noch kein Spieltest</small>`;
 $('prepared').checked=ready;$('prepared').disabled=true;
 markDirty();
 }catch(e){gameInfo=null;$('prepared').checked=false;$('gameStatus').innerHTML='<div class="notice bad">'+esc(e.message)+'</div>';throw e;}
}

async function uploadFiles(files){
 const moduleHint=pendingModule;pendingModule=null;
 await api('settings',settings());
 for(const file of files){
  const result=await busyJob(async()=>{const res=await fetch('/api/upload',{method:'POST',headers:{'X-TCS-Token':token,'X-TCS-Filename':encodeURIComponent(file.name),...(moduleHint?{'X-TCS-Module':moduleHint}:{}),'Content-Type':'application/octet-stream'},body:file});const data=await res.json();if(!res.ok)throw new Error(data.error);},'Importiere '+file.name);
  await loadState(false);
  // Backend retains a validated automatic mapping instead of resetting it to unconfirmed.
  renderDownloads();renderModules();
  if(result?.workflow?.status?.startsWith('INSTALLED')){showResult(result.workflow);step(5);}
 }
 markDirty(true);$('archiveInput').value='';
}
async function download(kind,name){const response=await fetch('/api/download?kind='+kind,{headers:{'X-TCS-Token':token}});if(!response.ok){const data=await response.json();throw new Error(data.error);}const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
async function preview(key){const result=await api('preview',{key});$('previewTitle').textContent=result.path;const host=$('previewContent');host.replaceChildren();const sections=result.variants.map(v=>({name:v.module+' · '+v.sha256.slice(0,12),text:v.text}));if(result.proposal!==null)sections.push({name:'Zusammengeführter Textvorschlag',text:result.proposal});for(const s of sections){const h=document.createElement('h3');h.textContent=s.name;host.appendChild(h);if(s.text===null){const p=document.createElement('p');p.className='muted';p.textContent='Binärdatei oder zu groß. Kein Text-Merge.';host.appendChild(p);}else{const text=document.createElement('textarea');text.readOnly=true;text.value=s.text;host.appendChild(text);}}$('previewDialog').showModal();}
async function handleClick(event){
 const b=event.target.closest('button,a');if(!b)return;
 if(b.dataset.step){step(Number(b.dataset.step));return;}
 if(b.dataset.uploadModule){pendingModule=b.dataset.uploadModule;$('archiveInput').click();return;}
 if(b.dataset.suggest){const m=app.profile.modules.find(x=>x.id===b.dataset.suggest),sel=app.state.selections[m.id],src=sourceById(sel.source_id);if(src){sel.roots=suggested(src.roots,m.root_mode);sel.confirmed=false;renderModules();markDirty(true);}return;}
 if(b.dataset.preview){await preview(b.dataset.preview);return;}
 switch(b.id){
 case 'chooseGameBtn':await selectFolder('gamePath');if($('gamePath').value)await checkGame();break;
 case 'chooseBaselineBtn':await selectFolder('baselinePath');break;
 case 'detectGameBtn':{const r=await api('detect',{});if(!r.paths.length)throw new Error('Keine passende Steam-Installation gefunden. Bitte „Ordner auswählen“ verwenden.');$('gamePath').value=r.paths[0];await checkGame();break;}
 case 'checkGameBtn':await checkGame();break;
 case 'addArchivesBtn':pendingModule=null;$('archiveInput').click();break;
 case 'addFolderBtn':{const p=app.platform==='nt'?(await api('picker',{kind:'folder'})).path:prompt('Vollständiger Pfad zum entpackten Modordner:');if(p){await busyJob(()=>api('import',{path:p}),'Prüfe Modordner');await loadState();markDirty();}break;}
 case 'saveSelectionsBtn':await api('settings',settings());step(4);break;
 case 'planBtn':await busyJob(()=>api('plan',settings()),'Vergleiche Dateien und Zusammenführungen');plan=await api('plan',null,'GET');dirty=false;conflictPage=0;renderPlan();await loadState(false);break;
 case 'downloadReportBtn':await download('report','TCS-Pruefbericht.json');break;
 case 'installBtn':if(!confirm('Die aufgelösten Dateien jetzt in die gewählte vorbereitete Spielkopie installieren? Betroffene Dateien werden gesichert. Spiel vorher schließen.'))return;{const r=await busyJob(()=>api('install',{plan_id:plan.id,confirmation:'INSTALL'}),'Sichere und installiere');await loadState();showResult(r);}break;
 case 'buildBtn':{const r=await busyJob(()=>api('build',{plan_id:plan.id}),'Baue lokale Mod-ZIP');await loadState();showResult(r);}break;
 case 'restoreBtn':if(confirm('Dateien der letzten Installation wiederherstellen? Später geänderte Dateien führen zu einem Stopp statt zu Datenverlust.')){const r=await busyJob(()=>api('restore',{game:$('gamePath').value.trim(),confirmation:'RESTORE'}),'Stelle Sicherungen wieder her');await loadState();showResult(r);markDirty();}break;
 case 'launchBtn':await startCheckedGame();break;
 case 'exportBtn':{const r=await api('export',{});await download('installer',r.name);break;}
 case 'openInstallerFolderBtn':await api('open-result',{kind:'installer'});break;
 case 'openBuildBtn':await api('open-result',{kind:'build'});break;
 case 'openGameBtn':await api('open-result',{kind:'game'});break;
 case 'prevPage':conflictPage--;renderConflicts();break;
 case 'nextPage':conflictPage++;renderConflicts();break;
 case 'closePreview':$('previewDialog').close();break;
 case 'hideProgressBtn':$('progress').hidden=true;break;
 case 'closeToast':$('toast').hidden=true;break;
 case 'shutdownBtn':if(confirm('Lokalen Assistenten beenden?')){await api('shutdown',{});document.body.innerHTML='<main style="padding:60px;font-family:system-ui"><h1>Assistent beendet.</h1><p>Dieses Browserfenster kann geschlossen werden.</p></main>';}break;
 }
}
function showResult(r){const installed=(r.status||'').startsWith('INSTALLED');const restored=r.status==='RESTORED';$('installResult').innerHTML=`<div class="panel" style="border-color:#3d7f68"><span class="success-icon">✓</span><h2>${restored?'Gesicherter Zustand wiederhergestellt':installed?'Dateien installiert':'Lokale Mod-ZIP erstellt'}</h2><span class="path">${esc(r.folder)}</span><p class="muted">${restored?'Betroffene Originaldateien wiederhergestellt.':installed?'Installation abgeschlossen. Ein erfolgreicher Spielstart und die Mod-Kompatibilität müssen jetzt im Spiel geprüft werden.':'Im geöffneten Buildordner die TCS-Remaster-Local.zip in Reloaded-II importieren. Grafikdateien aus graphics-for-game-folder separat ins Spielverzeichnis legen, falls ausgewählt.'}</p><button id="${installed||restored?'openGameBtn':'openBuildBtn'}">Ergebnisordner öffnen</button>${!restored?'<div class="notice">Dieser lokale Build enthält fremde Moddateien. Nicht öffentlich hochladen. Zum Weitergeben Schritt 6 benutzen.</div>':''}</div>`;}
function handleChange(event){const e=event.target;if(e.dataset.source){let sel=app.state.selections[e.dataset.source];const source=sourceById(e.value),m=app.profile.modules.find(x=>x.id===e.dataset.source);sel.source_id=e.value;sel.roots=source?suggested(source.roots,m.root_mode):[];sel.confirmed=false;renderModules();markDirty(true);return;}if(e.dataset.rootModule){const sel=app.state.selections[e.dataset.rootModule];sel.roots=e.checked?[...new Set([...sel.roots,e.dataset.root])]:sel.roots.filter(r=>r!==e.dataset.root);sel.confirmed=false;renderModules();markDirty(true);return;}if(e.dataset.confirm){app.state.selections[e.dataset.confirm].confirmed=e.checked;markDirty();return;}if(e.dataset.enabled){app.state.selections[e.dataset.enabled].enabled=e.checked;markDirty();return;}if(['gamePath','baselinePath','cleanTarget','prepared','baselineConfirmed','graphics'].includes(e.id))markDirty(['gamePath','baselinePath','baselineConfirmed'].includes(e.id));}
document.addEventListener('click',e=>handleClick(e).catch(error));document.addEventListener('change',handleChange);$('archiveInput').addEventListener('change',e=>uploadFiles([...e.target.files]).catch(error));$('conflictFilter').addEventListener('input',()=>{conflictPage=0;renderConflicts();});
for(const event of ['dragenter','dragover'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.add('drag');});for(const event of ['dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('drag');});$('dropzone').addEventListener('drop',e=>{pendingModule=null;uploadFiles([...e.dataTransfer.files]).catch(error);});
(async()=>{try{if(!token)throw new Error('Diese Seite über STARTEN.cmd öffnen. Eine normale HTML-Datei kann nicht selbstständig beliebige Dateien auf deinem PC verändern.');await loadState(true);step(nextStepNumber());if(app.job.running){await busyJob(async()=>{},'Laufenden Arbeitsschritt wieder verbinden');await loadState();}}catch(e){$('connectError').textContent=e.message+' Der lokale Helfer muss geöffnet bleiben.';$('connectError').hidden=false;}})();
