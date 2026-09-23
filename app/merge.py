"""Conservative three-way TEXT merge. This does not merge GSC/model binaries.
A conflict-free text result can be applied when the baseline is confirmed, but
it does not prove game-level correctness.
"""
from __future__ import annotations
import difflib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath

TEXT_EXTS={'.txt','.ini','.cfg','.json','.xml','.csv'}
MAX_TEXT=2*1024**2
@dataclass
class MergeResult:
    ok: bool
    data: bytes|None
    reason: str

def decode(data:bytes):
    if len(data)>MAX_TEXT: return None
    if data.startswith(b'\xef\xbb\xbf'):
        enc='utf-8-sig'
    elif data.startswith((b'\xff\xfe',b'\xfe\xff')):
        enc='utf-16'
    else:
        enc='utf-8'
        if b'\x00' in data: return None
    try:
        s=data.decode(enc)
        if any(ord(c)<32 and c not in '\r\n\t' for c in s): return None
        return s,enc
    except UnicodeError: return None

def _hunks(base,other):
    return [(a,b,tuple(other[c:d])) for op,a,b,c,d in difflib.SequenceMatcher(None,base,other,autojunk=False).get_opcodes() if op!='equal']

def _overlap(a,b):
    x,y,_=a; p,q,_=b
    if x==y and p==q: return x==p
    # Boundary insertions are conservatively considered ambiguous.
    if x==y: return p<=x<=q
    if p==q: return x<=p<=y
    return max(x,p)<min(y,q)

def merge3(base:bytes,left:bytes,right:bytes,path:str) -> MergeResult:
    if left==right: return MergeResult(True,left,'identical')
    if left==base: return MergeResult(True,right,'left-unchanged')
    if right==base: return MergeResult(True,left,'right-unchanged')
    if PurePosixPath(path).suffix.lower() not in TEXT_EXTS:
        return MergeResult(False,None,'Binär-/unbekanntes Format: passende Autoren-Patchdatei oder bewusste Variantenauswahl nötig.')
    decoded=[decode(b) for b in (base,left,right)]
    if any(d is None for d in decoded): return MergeResult(False,None,'Kein sicher lesbarer Text oder Datei zu groß für die Textprüfung.')
    (bs,enc),(ls,le),(rs,re)=decoded
    if enc!=le or enc!=re: return MergeResult(False,None,'Unterschiedliche Textkodierung; keine automatische Umwandlung.')
    b=bs.splitlines(keepends=True); l=ls.splitlines(keepends=True); r=rs.splitlines(keepends=True)
    if max(len(b),len(l),len(r))>12_000:
        return MergeResult(False,None,'Mehr als 12.000 Zeilen: manuelle Prüfung erforderlich.')
    lh=_hunks(b,l); rh=_hunks(b,r); all_hunks=list(lh)
    for h in rh:
        if h in lh: continue
        if any(_overlap(h,other) for other in lh):
            return MergeResult(False,None,'Beide Mods ändern dieselbe Textstelle. Es wird nichts geraten.')
        all_hunks.append(h)
    output=list(b)
    for start,end,replacement in sorted(all_hunks,key=lambda h:(h[0],h[1]),reverse=True):
        output[start:end]=replacement
    text=''.join(output)
    if path.lower().endswith('.json'):
        try: json.loads(text)
        except (ValueError,TypeError): return MergeResult(False,None,'Zusammenführung ergäbe ungültiges JSON.')
    return MergeResult(True,text.encode(enc),'Nicht überlappende Textänderungen vereint; Spiellogik ungeprüft.')
