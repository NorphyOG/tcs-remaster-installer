"""Official Nexus v1 API bridge, session-only credentials and strict NXM routing.
No page scraping, no login/password handling, no wait/paywall bypass. Free users
confirm downloads on Nexus; Premium may request direct links through the API.
"""
from __future__ import annotations
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode
from nettools import get_json, download, allowed_url
from safety import BuildError, MAX_ARCHIVE, no_links, digest

GAME = 'legostarwarsthecompletesaga'
BASE = 'https://api.nexusmods.com/v1'
ARCHIVE_ENDINGS={'.zip','.7z','.rar'}


def norm(text: str | None) -> str:
    if not isinstance(text,str): return ''
    return re.sub(r'[^a-z0-9]+',' ',text.lower()).strip()


def parse_nxm(url: str, allowed_mods: set[int], now=None) -> dict:
    if not isinstance(url,str): raise BuildError('NXM-Link fehlt oder ist ungültig.')
    if len(url)>8192: raise BuildError('NXM-Link ist zu lang.')
    u=urlsplit(url)
    if u.scheme!='nxm' or u.netloc!=GAME or u.username or u.password or u.fragment:
        raise BuildError('Dieser Assistent nimmt nur NXM-Links für Complete Saga an. Andere Spiele in ihrem Modmanager öffnen.')
    match=re.fullmatch(r'/mods/([1-9]\d*)/files/([1-9]\d*)/?',u.path)
    if not match: raise BuildError('Ungültiger Nexus-Dateilink.')
    mod_id,file_id=map(int,match.groups())
    if mod_id not in allowed_mods: raise BuildError('Diese Mod gehört nicht zum geprüften Installer-Rezept.')
    q=parse_qs(u.query,keep_blank_values=True)
    if any(len(v)!=1 for v in q.values()) or set(q)-{'key','expires','user_id','view'}:
        raise BuildError('Unbekannte oder doppelte NXM-Parameter.')
    result={'mod_id':mod_id,'file_id':file_id}
    if 'key' in q or 'expires' in q:
        if not {'key','expires'}<=set(q): raise BuildError('Unvollständige Nexus-Downloadfreigabe.')
        key=q['key'][0]
        if not re.fullmatch(r'[A-Za-z0-9_\-+=/.]{1,2048}',key): raise BuildError('Ungültige Nexus-Downloadfreigabe.')
        try: expires=int(q['expires'][0])
        except ValueError: raise BuildError('Ungültige Ablaufzeit.') from None
        if expires <= (time.time() if now is None else now): raise BuildError('Nexus-Link abgelaufen. Download im Browser erneut bestätigen.')
        result.update(key=key,expires=expires)
    if 'user_id' in q:
        if not q['user_id'][0].isdecimal(): raise BuildError('Ungültige Nexus-Nutzerzuordnung.')
        result['user_id']=int(q['user_id'][0])
    return result


class Nexus:
    def __init__(self, profile: dict, local: Path):
        self.profile=profile; self.local=local; self._key=None; self._user=None; self.catalog={}
    def status(self):
        return {'connected':bool(self._key),'premium':bool(self._user and self._user.get('is_premium')),
                'name':(self._user or {}).get('name',''), 'files_resolved':len(self.catalog),
                'credentials':'session_memory_only'}
    def api(self, path: str):
        if not self._key: raise BuildError('Zuerst den persönlichen Nexus-API-Schlüssel verbinden. Alternativ den Downloadordner beobachten.')
        return get_json(BASE+path, purpose='api',headers={
            'apikey':self._key,'Application-Name':'TCS Remaster Community Installer',
            'Application-Version':'0.4.0','Accept':'application/json'})
    def connect(self, key: str):
        if not isinstance(key,str) or not 10<=len(key.strip())<=1024 or any(ord(c)<33 or ord(c)>126 for c in key.strip()):
            raise BuildError('Einen gültigen persönlichen Nexus-API-Schlüssel eingeben; kein Passwort.')
        self._key=key.strip(); self._user=None; self.catalog={}
        try:
            user=self.api('/users/validate.json')
            if not isinstance(user,dict) or not isinstance(user.get('user_id'),int): raise BuildError('Nexus konnte das Konto nicht bestätigen.')
            # Do not keep/email/log API response fields such as email or api key.
            self._user={k:user.get(k) for k in ('user_id','name','is_premium')}
        except Exception:
            self._key=None; raise
        return self.status()
    def disconnect(self):
        self._key=None; self._user=None; self.catalog={}
        return self.status()
    def resolve(self, log=print):
        self.catalog={}; checked={}; missing=[]
        for module in self.profile['modules']:
            nx=module.get('nexus')
            if not nx: continue
            mod=nx['mod_id']
            if mod not in checked:
                response=self.api(f'/games/{GAME}/mods/{mod}/files.json')
                if not isinstance(response,dict) or not isinstance(response.get('files'),list): raise BuildError('Unerwartete Nexus-Dateiliste.')
                checked[mod]=response['files']
            found=[]
            for f in checked[mod]:
                if not isinstance(f,dict): continue
                if str(f.get('category_name','')).upper() in ('OLD_VERSION','OLD VERSIONS','ARCHIVED','REMOVED') or f.get('category_id') in (4,6,7): continue
                if nx.get('file_id'):
                    if f.get('file_id')!=nx['file_id']: continue
                elif norm(f.get('name',''))!=norm(nx['file_name']): continue
                version=str(f.get('version') or '').strip()
                if nx.get('file_version') and version!=nx['file_version']: continue
                if not isinstance(f.get('file_name'),str): continue
                if not isinstance(f.get('file_id'),int) or Path(f.get('file_name') or '').suffix.lower() not in ARCHIVE_ENDINGS: continue
                found.append(f)
            if len(found)!=1:
                missing.append({'module':module['id'],'reason':'Datei nicht eindeutig oder Version geändert. Autorendownload manuell prüfen.'})
                continue
            f=found[0]
            self.catalog[module['id']]={'module':module['id'],'mod_id':mod,'file_id':f['file_id'],
                'name':f.get('name') or module['name'],'file_name':f['file_name'],'version':str(f.get('version') or ''),
                'download_page':f'https://www.nexusmods.com/{GAME}/mods/{mod}?tab=files&file_id={f["file_id"]}',
                'size_bytes':f.get('size_in_bytes')}
            log('Originaldatei identifiziert: '+module['name'])
        return {'files':list(self.catalog.values()),'needs_review':missing}
    def fetch(self, module_id: str, log=print, signed: dict | None=None):
        if module_id not in self.catalog: self.resolve(log)
        item=self.catalog.get(module_id)
        if not item: raise BuildError('Moddatei nicht eindeutig auf Nexus aufgelöst. Manuellen Autorendownload verwenden.')
        if signed:
            if signed['mod_id']!=item['mod_id'] or signed['file_id']!=item['file_id']:
                raise BuildError('NXM-Link passt nicht zur ausgewählten Rezeptdatei.')
            if signed.get('user_id') and signed['user_id']!=(self._user or {}).get('user_id'):
                raise BuildError('NXM-Link gehört zu einem anderen Nexus-Konto.')
        if not self.status()['premium'] and not (signed and signed.get('key')):
            raise BuildError('Kostenloses Nexus-Konto: Download auf der Originalseite bestätigen. Danach automatisch per Downloadordner oder gültigem NXM-Link übernehmen.')
        path=f'/games/{GAME}/mods/{item["mod_id"]}/files/{item["file_id"]}/download_link.json'
        if signed and signed.get('key'): path+='?'+urlencode({'key':signed['key'],'expires':signed['expires']})
        response=self.api(path)
        if not isinstance(response,list) or not response: raise BuildError('Nexus hat keinen Download freigegeben.')
        links=[item for item in response if isinstance(item,dict) and isinstance(item.get('URI'),str)]
        if not links: raise BuildError('Nexus hat keine gültige Downloadadresse geliefert. Bitte erneut versuchen.')
        url=links[0]['URI']
        if not isinstance(url,str): raise BuildError('Downloadantwort enthält keine freigegebene URL.')
        allowed_url(url,'mod')
        ext=Path(item['file_name']).suffix.lower()
        target=self.local/'imports'/('nexus-'+uuid.uuid4().hex+ext)
        log('Download: '+item['name'])
        receipt=download(url,target,purpose='mod',maximum=MAX_ARCHIVE,log=log)
        # Signed CDN URLs and API keys are deliberately absent from the receipt.
        return {'path':str(target),'display_name':item['file_name'],'nexus':dict(item),'download':receipt}
    def receive(self, url: str, log=print):
        signed=parse_nxm(url,{m['nexus']['mod_id'] for m in self.profile['modules'] if m.get('nexus')})
        if not self.catalog: self.resolve(log)
        items=[key for key,item in self.catalog.items() if item['mod_id']==signed['mod_id'] and item['file_id']==signed['file_id']]
        if len(items)!=1: raise BuildError('Diese optionale/ältere Nexus-Datei ist nicht Teil der aktiv unterstützten Installation.')
        return self.fetch(items[0],log,signed)


class DownloadWatch:
    """Explicitly selected folder only. No in-progress downloads, no recursive scan.
    Filename matches identify candidates, not authenticity. Import/variant review
    still happens; explicit consent permits unambiguous recipe auto-mapping.
    """
    def __init__(self, profile):
        self.profile=profile; self.seen={}; self.done={}; self.failed={}
    def candidates(self, folder: str, now=None) -> list[dict]:
        p=no_links(Path(folder).absolute())
        if not p.is_dir(): raise BuildError('Downloadordner nicht gefunden.')
        now=time.monotonic() if now is None else now
        candidates=[]
        for f in p.iterdir():
            if not f.is_file() or f.suffix.lower() not in ARCHIVE_ENDINGS: continue
            no_links(f); stat=f.stat()
            if not 0<stat.st_size<=MAX_ARCHIVE: continue
            lower=norm(f.stem)
            matches=[]
            for m in self.profile['modules']:
                aliases=m.get('watch_names',[])
                if any(norm(alias) and norm(alias) in lower for alias in aliases): matches.append(m['id'])
            if len(matches)!=1: continue
            key=str(f); signature=(stat.st_size,stat.st_mtime_ns)
            previous=self.seen.get(key)
            if not previous or previous[0]!=signature:
                self.seen[key]=(signature,now); continue
            if now-previous[1]<8 or self.done.get(key)==signature or self.failed.get(key)==signature: continue
            if any(f.with_name(f.name+ext).exists() for ext in ('.part','.crdownload','.download','.tmp')): continue
            candidates.append({'path':key,'module':matches[0],'signature':signature,'bytes':stat.st_size})
        return candidates
    def mark_done(self, candidate): self.done[candidate['path']]=candidate['signature']

    def mark_failed(self, item):
        self.failed[item['path']]=item['signature']
    def retry_failed(self):
        self.failed.clear()
