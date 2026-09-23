"""Recipe matching without assuming filenames prove authenticity."""
from __future__ import annotations
import re
from pathlib import Path

def normalize(value):
    return re.sub(r'[^a-z0-9]+',' ',value.lower()).strip() if isinstance(value,str) else ''

def identify(name, modules):
    text=normalize(Path(name).stem)
    found=[m for m in modules if any(normalize(alias) and normalize(alias) in text
                                   for alias in m.get('watch_names',[]))]
    return found[0] if len(found)==1 else None

def filename_version(name, module):
    """Nexus filename suffix, including Windows '(1)' duplicate-download suffix."""
    stem=re.sub(r' \(\d+\)$','',Path(name).stem)
    mod_id=module.get('nexus',{}).get('mod_id')
    match=re.search(r'-'+str(mod_id)+r'-(.+)-(\d{9,11})$',stem)
    if not match:return None
    return match.group(1).replace('-','.')

def assess(name,module,metadata=None):
    version=(metadata or {}).get('version') or filename_version(name,module)
    expected=module.get('nexus',{}).get('file_version')
    match_name=any(normalize(a) and normalize(a) in normalize(name) for a in module.get('watch_names',[]))
    if metadata:
        match_name=metadata.get('mod_id')==module.get('nexus',{}).get('mod_id') and metadata.get('module')==module['id']
    reason=''
    if not match_name:reason='Archivname passt nicht zu dieser Rezeptdatei. Richtige Downloadkarte verwenden.'
    elif expected and version and version!=expected:
        reason=f'Andere Dateiversion erkannt: {version}; Rezept erwartet {expected}. Nicht ungeprüft ersetzen.'
    return {'matches':not reason,'reason':reason,'observed_version':version,
            'expected_version':expected,'authenticity_verified':False}

def roots_for_recipe(roots,mode):
    if not roots:return []
    parts=[r.split('/') if r else [] for r in roots]
    common_prefix=0
    if len(parts)>1:
        while all(len(p)>common_prefix for p in parts) and len({p[common_prefix] for p in parts})==1:
            common_prefix+=1
    def flags(root):
        value=normalize('/'.join((root.split('/') if root else [])[common_prefix:]))
        return {'classic':'classic' in value,'icon':'icon' in value,
                'excluded':any(w in value for w in ('optional','film accurate','e3 2019','modern icon','mo icon','alternate','alternativ'))}
    flagged=[(r,flags(r)) for r in roots]
    common=[r for r,f in flagged if not f['classic'] and not f['icon'] and not f['excluded']]
    classic=[r for r,f in flagged if f['classic'] and not f['excluded']]
    if mode=='classic':
        if len(common)==1 and len(classic)==1:return [common[0],classic[0]]
        if len(classic)==1 and not common:return [classic[0]]
        return []
    return common if len(common)==1 and not classic else []
