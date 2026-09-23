'use strict';
let lastJobId='', autoSyncing=false,autoPollBusy=false,nexusFiles=new Map(),lastObservedImport=null,lastRenderedJob='';
function recordObservedJob(job){if(job?.id&&!job.running)lastJobId=job.id;}
function recordObservedState(state){recordObservedJob(state.job);const event=state.workflow?.last_import?.event_id;if(event)lastObservedImport=event;}
function autoPayload(){return {allow_tools:$('allowTools').checked,auto_mapping:$('autoMapping').checked,desktop_shortcut:$('desktopShortcut').checked,auto_watch:$('autoWatchDownloads').checked,auto_nexus:$('autoNexusDownloads').checked};}
async function saveAuto(){await api('settings',settings());return api('automation/settings',autoPayload());}
function renderAuto(status,fill=false){
 const a=status.automation,n=status.nexus;
 if(typeof renderInventory==='function')renderInventory(status.inventory||[]);
 const planReady=plan&&!dirty&&!plan.counts.conflicts,installed=!!app?.state.installed_game;
 $('autoMessage').textContent=installed?installedSummary().message:planReady?'Bekannte Dateikollisionen automatisch geregelt. Installation und Spieltest stehen noch aus.':status.message;
 $('autoHeadline').textContent=installed?installedSummary().headline:planReady?'Dateiplan bereit · als Nächstes installieren':a.armed?'Automatik wartet oder installiert nach Prüfung.':'Spielvorbereitung und Downloadübergabe';
 $('autoBadge').textContent=a.armed?'Automatik aktiv':'Kontrollierter Modus';
 $('autoBadge').className='pill'+(a.armed?' good':'');
 $('nexusStatus').textContent=n.connected?'Verbunden: '+n.name+' · '+(n.premium?'Premium-Direktdownloads möglich':'Kostenlos · Browserbestätigung nötig'):'Nicht verbunden · Downloadordner funktioniert auch ohne API-Schlüssel.';
 $('watchStatus').textContent=status.watch_paused?'Übernahme pausiert. Fehler prüfen und mit „Erneut versuchen / fortsetzen“ neu starten.':a.watch_enabled?'Beobachtet: '+(status.watch_folders||[a.watch_folder]).join(' + ')+' · nur abgeschlossene Archive':'Downloadübernahme ist ausgeschaltet.';
 $('nexusAllBtn').disabled=!n.connected||!n.premium;
 $('autoDownloadFolder').textContent=a.watch_folder?'Downloadordner: '+a.watch_folder:'Kein Downloadordner erkannt. In Schritt 2 auswählen oder Archive hineinziehen.';
 const protocol=status.nxm_protocol;
 $('nxmStatus').textContent=protocol.registered?'NXM-Zuordnung eingerichtet. Vorherige Zuordnung ist lokal gesichert.':protocol.handler?'Bisheriger NXM-Handler: '+protocol.handler:'Noch keine NXM-Zuordnung erkannt. Downloadordner ist die einfachere Alternative.';
 if(fill){autoSyncing=true;for(const [id,key] of [['allowTools','allow_tools'],['autoMapping','auto_mapping'],['desktopShortcut','desktop_shortcut'],['autoWatchDownloads','auto_watch'],['autoNexusDownloads','auto_nexus']])$(id).checked=!!a[key];$('watchFolder').value=a.watch_folder||'';autoSyncing=false;}
}
async function refreshAuto(fill=false){const status=await api('automation/status',null,'GET');renderAuto(status,fill);return status;}
async function afterAutoJob(result,background=false){
 await loadState(!background,background);await refreshAuto(!background);markDirty();
 const outcome=result?.workflow||result;
 if(outcome?.status?.startsWith('INSTALLED')){showResult(outcome);step(5);}
 else if(outcome?.conflicts){plan=await api('plan',null,'GET');dirty=false;renderPlan();step(4);}
}
async function autoClick(event){
 const b=event.target.closest('button');if(!b)return;
 if(b.dataset.nexusModule){
  await saveAuto();const status=await refreshAuto();
  if(status.nexus.connected&&status.nexus.premium){const r=await busyJob(()=>api('nexus/download',{module:b.dataset.nexusModule}),'Mod vom Autor laden und übernehmen');await afterAutoJob(r);}
  else{const m=app.profile.modules.find(m=>m.id===b.dataset.nexusModule);const file=nexusFiles.get(m.id);await api('open-download',{module:m.id});$('autoMessage').textContent='Download auf Nexus bestätigen. Den gewählten Downloadordner beobachten lassen oder das fertige Archiv hinzufügen.';}
  return;
 }
 switch(b.id){
  case 'prepareBtn':{
   await checkGame();await saveAuto();
   if(!confirm('Die eigene Steam-Kopie jetzt prüfen und vorbereiten? Original-DATs werden erst nach erfolgreichem Entpacken gesichert. EXE und Spielstände bleiben unverändert.'))return;
   const r=await busyJob(()=>api('prepare',{game:$('gamePath').value.trim(),confirmation:'PREPARE'}),'Originalspiel automatisch vorbereiten');await afterAutoJob(r);await checkGame();break;
  }
  case 'autoStartBtn':{
   await checkGame();await saveAuto();
   if(!confirm('Automatik starten? Der Assistent bereitet die gewählte saubere Spielkopie vor und installiert danach die aktivierten, bestätigten Archive, sobald der Dateiplan konfliktfrei ist. Originale werden gesichert. Unklare Änderungen stoppen die Installation.'))return;
   const r=await busyJob(()=>api('automation/start',{confirmation:'PREPARE_AND_INSTALL'}),'Vorbereitung + kontrollierte Automatik');await afterAutoJob(r);if(!r?.status?.startsWith('INSTALLED')){await checkGame();step(2);}break;
  }
  case 'autoContinueBtn':{
   await saveAuto();if(!confirm('Automatik mit der aktuellen bestätigten Auswahl fortsetzen?'))return;
   const r=await busyJob(()=>api('automation/continue',{confirmation:'CONTINUE'}),'Automatik fortsetzen');await afterAutoJob(r);break;
  }
  case 'autoStopBtn':case 'pauseJobBtn':await api('automation/stop',{});await refreshAuto(true);break;
  case 'diagnosticBtn':await download('diagnostics','TCS-Diagnose-0.4.0.json');break;
  case 'retryWorkflowBtn':{
   await checkGame();await saveAuto();
   if(!confirm('Automatik erneut starten? Vorhandene Zwischenschritte werden geprüft und wiederverwendet. Fehlende Dateien werden nachgeladen bzw. aus dem Downloadordner übernommen. Dateien werden nur nach erfolgreicher Prüfung installiert.'))return;
   const r=await busyJob(()=>api('automation/continue',{confirmation:'CONTINUE'}),'Vorbereitung fortsetzen');await afterAutoJob(r);if(r?.waiting&&!r?.conflicts)step(2);break;
  }
  case 'watchChooseBtn':{const r=await api('picker',{kind:'folder'});if(r.path)$('watchFolder').value=r.path;break;}
  case 'watchEnableBtn':await saveAuto();await api('automation/settings',{watch_enabled:true,watch_folder:$('watchFolder').value.trim()});await refreshAuto();break;
  case 'nexusConnectBtn':{
   const key=$('nexusKey').value;$('nexusKey').value='';
   await api('nexus/connect',{key});await refreshAuto();$('toast').hidden=true;break;
  }
  case 'nexusDisconnectBtn':await api('nexus/disconnect',{});nexusFiles.clear();$('nexusFilesResult').replaceChildren();await refreshAuto();break;
  case 'nexusFilesBtn':{
   const r=await busyJob(()=>api('nexus/files',{}),'Haupt- und Optionaldateien bei Nexus abgleichen');nexusFiles=new Map(r.files.map(f=>[f.module,f]));
   $('nexusFilesResult').innerHTML=r.files.map(f=>`<div class="listline"><strong>${esc(f.name)}</strong><span>Version ${esc(f.version||'nicht angegeben')} · Datei ${f.file_id}</span></div>`).join('')+(r.needs_review.length?'<div class="notice">'+r.needs_review.map(m=>esc(m.module)+': '+esc(m.reason)).join('<br>')+'</div>':'');await refreshAuto();break;
  }
  case 'nexusAllBtn':{
   await saveAuto();const r=await busyJob(()=>api('nexus/download-selected',{}),'Aktivierte Archive laden');await afterAutoJob(r);break;
  }
  case 'nxmRegisterBtn':{
   const status=await refreshAuto();
   if(!confirm('NXM ist eine globale URL-Zuordnung für diesen Windows-Benutzer. Eine vorhandene Vortex-Zuordnung wird gesichert und durch diesen TCS-Handler ersetzt; andere Spiele werden hier nicht verarbeitet.\n\nBisher: '+(status.nxm_protocol.handler||'keine')+'\n\nTrotzdem ausdrücklich registrieren?'))return;
   await api('nxm/register',{confirmation:'REGISTER_NXM'});await refreshAuto();break;
  }
  case 'nxmRestoreBtn':await api('nxm/unregister',{});await refreshAuto();break;
  case 'quickbmsFileBtn':{const r=await api('picker',{kind:'file'});if(r.path)await busyJob(()=>api('tools/quickbms',{path:r.path}),'Offizielles QuickBMS-ZIP hashprüfen');break;}
  case 'setup7zipBtn':await saveAuto();await busyJob(()=>api('tools/sevenzip',{}),'7-Zip aus der offiziellen Quelle einrichten');await loadState();break;
  case 'shortcutsBtn':if(confirm('Spiel- und Verwaltungsverknüpfung auf dem Desktop erstellen? Bestehende Verknüpfungen werden nicht überschrieben.')){const r=await api('shortcuts',{game:$('gamePath').value.trim(),confirmation:'CREATE_SHORTCUTS'});$('autoMessage').textContent='Verknüpfung erstellt: '+r.shortcut;}break;
  case 'restorePrepBtn':{
   if(!confirm('Originalvorbereitung zurücksetzen? Zuerst einen installierten Modbuild wiederherstellen. Danach kommen die gesicherten DATs zurück; nur unveränderte, von uns erzeugte lose Dateien werden entfernt.'))return;
   const r=await busyJob(()=>api('prepare/restore',{game:$('gamePath').value.trim(),confirmation:'RESTORE_PREPARATION'}),'Original-DATs wiederherstellen');await afterAutoJob(r);await checkGame();break;
  }
 }
}
document.addEventListener('click',e=>autoClick(e).catch(error));
document.addEventListener('change',e=>{
 if(autoSyncing||!app)return;
 if(['allowTools','autoMapping','desktopShortcut','autoWatchDownloads','autoNexusDownloads'].includes(e.target.id))api('automation/settings',autoPayload()).then(r=>renderAuto(r)).catch(error);
 if(e.target.dataset.enabled==='ep3-additions'){
  const enabled=e.target.checked;app.state.selections['infinities-vader-patch'].enabled=enabled;renderModules();markDirty();
 }
});
(async()=>{
 for(let i=0;i<100&&!app;i++)await sleep(100);if(!app)return;
 try{
  await refreshAuto(true);renderJob(app.job);
  if(!$('gamePath').value){const d=await api('defaults',{});if(d.games?.length===1){$('gamePath').value=d.games[0];await checkGame();}}
  const audit=await api('audit',null,'GET');
  $('auditTable').innerHTML='<div class="audit-scroll"><table class="audit-table"><thead><tr><th>Datei / Version</th><th>Entscheidung</th><th>Warum / Voraussetzung</th></tr></thead><tbody>'+audit.items.map(r=>`<tr><td><a href="${esc(r.source)}" target="_blank" rel="noopener noreferrer">${esc(r.file)}</a><br><small>${esc(r.version)}</small></td><td>${esc(r.decision)}</td><td>${esc(r.reason)}${r.requires?'<br><small>Benötigt: '+esc(r.requires)+'</small>':''}</td></tr>`).join('')+'</tbody></table></div>';
 }catch(e){error(e);}
 setInterval(async()=>{
  if(autoPollBusy||document.body.classList.contains('busy')||!$('autoMessage'))return;
  autoPollBusy=true;
  try{
   const status=await refreshAuto();const job=await api('job',null,'GET');
   if(document.body.classList.contains('busy'))return;
   renderJob(job);
   const importEvent=status.last_import?.event_id||null;
   if(importEvent&&importEvent!==lastObservedImport&&!job.running){await loadState(false,true);markDirty();}
   if(!job.running&&job.id&&job.id!==lastJobId){lastJobId=job.id;if(job.result&&!job.error)await afterAutoJob(job.result,true);}
   if(job.running){const r=await busyJob(async()=>{},'Automatischer Download / Import');await afterAutoJob(r,true);}
  }catch(e){error(e);}finally{autoPollBusy=false;}
 },3500);
})();

function renderJob(job){
 if(!job||!$('jobPanel'))return;
 const snapshot=JSON.stringify(job);
 if(snapshot===lastRenderedJob)return;
 lastRenderedJob=snapshot;
 if(job.steps&&typeof renderJourney==='function')renderJourney(job.steps);
 const visible=!!(job.id||job.error||(job.logs||[]).length);
 $('jobPanel').hidden=!visible;if(!visible)return;
 const active=job.running||!!job.error||['waiting','cancelled','interrupted'].includes(job.status);
 const main=document.querySelector('main.main'),panel=$('jobPanel');
 main.insertBefore(panel,active?$('step1'):$('journeyPanel'));
 $('jobPhase').textContent=job.status==='success'?'Letzter Auftrag abgeschlossen':job.phase_label||'Arbeitsschritt';
 const labels={running:'Arbeitet',error:'Pausiert · Fehler',cancelled:'Pausiert',interrupted:'Unterbrochen',waiting:'Wartet auf Downloads / Prüfung',success:'Arbeitsschritt abgeschlossen',idle:'Bereit'};
 $('jobStatus').textContent=labels[job.status]||'Status';
 $('jobStatus').className='pill'+(job.error?' bad':job.status==='success'?' good':'');
 $('jobError').hidden=!job.error;$('jobError').textContent=job.error?(job.error+(job.error_id?' · Diagnose-ID '+job.error_id:'')+(job.recovery?.instruction?' '+job.recovery.instruction:'')):'';
 const pak=job.pak_checks;
 $('pakCheckStatus').hidden=!pak;
 if(pak){
  $('pakCheckStatus').textContent='PAK-Dateigrenzen geprüft · '+Number(pak.archives_checked||0).toLocaleString('de-DE')+' Archive · '+Number(pak.short_entries||0).toLocaleString('de-DE')+' kurze Einträge unter 32 Bytes berücksichtigt. Keine Dateien aufgefüllt oder Fehlercodes ignoriert.';
 }
 const filter=job.original_filter;
 $('originalFilterStatus').hidden=!filter;
 if(filter){
  const n=Number(filter.excluded_count||0);
  $('originalFilterStatus').textContent='Originaldaten-Filter aktiv · '+n.toLocaleString('de-DE')+' Programmdatei(en) nicht entpackt / nicht installiert.'+(n?' '+(filter.samples||[]).slice(0,5).join(', ')+(n>5?' …':''):'')+' Vorhandene EXE-/DLL-Dateien bleiben unverändert.';
 }
 $('retryWorkflowBtn').hidden=job.running||!(['error','cancelled','interrupted','waiting'].includes(job.status));
 $('pauseJobBtn').hidden=!(job.running||job.status==='waiting');
 const p=job.progress;
 $('jobMeter').hidden=true;$('jobCounts').textContent='';
 if(p){
  const format=(n)=>Number(n||0).toLocaleString('de-DE');
  const show=(n)=>p.unit==='Bytes'?format(Math.round(n/1024/1024))+' MiB':format(n)+' '+p.unit;
  $('jobCounts').textContent=show(p.done)+(p.total?' / '+show(p.total):'');
  if(p.total>0)$('jobMeterFill').style.width=Math.min(100,100*p.done/p.total)+'%';
 }
 const history=$('jobHistory');const nearBottom=history.scrollHeight-history.scrollTop-history.clientHeight<60;
 history.textContent=(job.logs||[]).join('\n');if(nearBottom)history.scrollTop=history.scrollHeight;
 if(job.error)$('jobDetails').open=true;
}
