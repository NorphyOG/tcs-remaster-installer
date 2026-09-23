'use strict';
const stageStatus={pending:'Noch offen',running:'Läuft',waiting:'Wartet',done:'Fertig',error:'Prüfung nötig',paused:'Pausiert'};
let lastJourneySnapshot='',lastInventorySnapshot='';
function renderJourney(data){
 if(!data||!$('journeyStages'))return;
 const snapshot=JSON.stringify(data)+String(!!app?.state.readiness?.user_reported_game_test);
 if(snapshot===lastJourneySnapshot)return;
 lastJourneySnapshot=snapshot;
 $('journeyCount').textContent=`${data.completed} / ${data.total} Schritte fertig`;
 $('journeySegments').innerHTML=data.stages.map(s=>`<span class="${esc(s.status)}"></span>`).join('');
 $('journeyStages').innerHTML=data.stages.map((s,i)=>{
  const p=s.progress, known=!!(p&&Number.isFinite(p.total)&&p.total>0&&Number.isFinite(p.done));
  const percent=s.status==='done'?100:known?Math.min(100,Math.max(0,p.done/p.total*100)):0;
  const label=s.status==='done'?'100 %':known?Math.round(percent)+' % Teilaufgabe':s.status==='running'?'Gesamtmenge noch offen':stageStatus[s.status];
  const fmt=n=>Number(n).toLocaleString('de-DE');
  const counts=known?`${fmt(p.done)} / ${fmt(p.total)} ${p.unit==='Bytes'?'Bytes':p.unit}`:'';
  const detail=s.id==='verify'&&app?.state.readiness?.user_reported_game_test?'Dateien geprüft; Spieltest vom Benutzer bestätigt.':s.detail;
  return `<article class="stage-card ${esc(s.status)}" data-stage="${esc(s.id)}"><div class="stage-title"><span class="stage-number">${s.status==='done'?'✓':String(i+1).padStart(2,'0')}</span><strong>${esc(s.title)}</strong><span class="stage-label">${esc(stageStatus[s.status])}</span></div><div class="stage-meter ${!known&&s.status==='running'?'unmeasured':''}" role="progressbar" aria-label="${esc(s.title)}" ${known||s.status==='done'?`aria-valuenow="${Math.round(percent)}" aria-valuemin="0" aria-valuemax="100"`:''} aria-valuetext="${esc(label)}"><span style="width:${percent}%"></span></div><div class="stage-value"><b>${esc(label)}</b><small>${esc(counts)}</small></div><p class="stage-detail">${esc(detail)}</p></article>`;
 }).join('');
}
function renderInventory(rows){
 if(!$('inventoryStatus'))return;
 const snapshot=JSON.stringify(rows);
 if(snapshot===lastInventorySnapshot)return;
 lastInventorySnapshot=snapshot;
 $('inventoryStatus').innerHTML=rows.filter(r=>r.enabled||r.imported).map(r=>`<div><strong>${esc(r.name)}</strong><span class="pill ${r.ready?'good':''}">${!r.enabled?'Optional · nicht aktiv':r.ready?'Zugeordnet':r.imported?'Prüfen':'Download fehlt'}</span>${r.review_reason?`<small>${esc(r.review_reason)}</small>`:''}</div>`).join('');
}
function renderReadiness(){
 if(!app||!$('readinessStatus'))return;
 const r=app.state.readiness;
 $('playCheckedBtn').disabled=!app.state.installed_game||document.body.classList.contains('busy');
 $('confirmGameBtn').disabled=!r?.launch_requested||!!r?.user_reported_game_test;
 $('confirmGameBtn').textContent=r?.user_reported_game_test?'Spieltest bestätigt':'Spiel & Mods funktionieren';
 $('readinessStatus').textContent=r?.can_launch?`${r.checked_files} installierte Dateien geprüft. ${r.user_reported_game_test?'Spieltest vom Benutzer bestätigt.':r.launch_requested?'Startbefehl gesendet; Spieltest noch bestätigen.':'Spieltest noch offen.'}`+(r.warnings?.length?' '+r.warnings.join(' '):''):'Erst installieren. Anschließend wird jede Moddatei gegen das Installationsjournal geprüft.';
}
async function startCheckedGame(){
 const result=await busyJob(()=>api('launch',{confirmation:'LAUNCH'}),'Installationsprüfung und Spielstart');
 await loadState(false);renderReadiness();$('autoMessage').textContent=result.note;
}
async function nextDownload(){
 await saveAuto();
 const status=await api('automation/status',null,'GET');
 const missing=status.inventory.find(r=>r.enabled&&!r.imported);
 if(!missing){$('autoMessage').textContent='Alle aktivierten Archive sind vorhanden. Offene Zuordnungen in Schritt 3 prüfen.';step(3);return;}
 await api('automation/settings',{watch_enabled:true,watch_local_mods:true});
 await api('open-download',{module:missing.id});
 $('autoMessage').textContent='Im Browser herunterladen: '+missing.name+'. Anschließend übernimmt der Assistent das fertige Archiv.';
 await refreshAuto();
}
document.addEventListener('click',event=>{
 const b=event.target.closest('button');if(!b)return;
 (async()=>{
  if(b.dataset.openModule){await saveAuto();await api('automation/settings',{watch_enabled:true,watch_local_mods:true});await api('open-download',{module:b.dataset.openModule});await refreshAuto();return;}
  if(b.id==='nextDownloadBtn')return nextDownload();
  if(b.id==='watchLocalBtn'){await api('automation/settings',{watch_enabled:true,watch_local_mods:true});await refreshAuto();return;}
  if(b.id==='verifyBtn'){await busyJob(()=>api('verify',{}),'Installierte Dateien prüfen');await loadState(false);renderReadiness();}
  if(b.id==='playCheckedBtn')return startCheckedGame();
  if(b.id==='confirmGameBtn'){
   await api('game-tested',{confirmation:'GAME_AND_MODS_TESTED'});await loadState(false);
  }
 })().catch(error);
});
(async()=>{for(let i=0;i<100&&!app;i++)await sleep(100);if(app){renderJourney(app.steps);renderInventory(app.workflow?.inventory||[]);renderReadiness();}})();
