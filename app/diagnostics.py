"""Local, redacted diagnostics and optional progress callbacks. No telemetry."""
from __future__ import annotations
import re
import traceback
from pathlib import Path
from safety import BuildError

class Cancelled(BuildError):
    """Cancellation at a read/staging boundary, never in the middle of a commit."""


def check_cancel(log):
    fn = getattr(log, 'check_cancelled', None)
    if callable(fn): fn()


def phase(log, key, label):
    fn = getattr(log, 'phase', None)
    if callable(fn): fn(key, label)
    else: log(label)


def progress(log, done, total, unit='Dateien'):
    fn = getattr(log, 'progress', None)
    if callable(fn): fn(done, total, unit)


def redact(text, paths=(), secrets=()):
    value = str(text)
    for secret in secrets:
        if isinstance(secret, str) and secret:
            value = value.replace(secret, '[SCHLUESSEL]')
    # Never export signed NXM/CDN/API query strings or our local session fragment.
    value = re.sub(r'\b(?:https?|nxm)://[^\s<>"\']+', '[URL_ENTFERNT]', value)
    value = re.sub(r'(?i)(apikey|api_key|authorization|token|password|key)\s*[:=]\s*["\']?[^\s,;"\']+', r'\1=[ENTFERNT]', value)
    replacements = []
    for path, label in paths:
        if isinstance(path, (str, Path)) and str(path):
            replacements.extend([(str(path), label), (str(path).replace('\\','/'), label), (str(path).replace('\\','\\\\'), label)])
    for path, label in sorted(replacements, key=lambda r: -len(r[0])):
        value = re.sub(re.escape(path), lambda _: label, value, flags=re.I)
    # Redact remaining user profile prefixes without exposing a username.
    value = re.sub(r'(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s"\']+', '[BENUTZER]', value)
    value = re.sub(r'/home/[^/\s"\']+|/Users/[^/\s"\']+', '[BENUTZER]', value)
    return value


def error_record(exc, job, paths=(), secrets=()):
    controlled = isinstance(exc, BuildError)
    cancelled = isinstance(exc, Cancelled)
    technical = redact(str(exc) or type(exc).__name__, paths, secrets)
    message = technical if controlled else 'Interner Fehler im Schritt „'+job.get('phase_label','Arbeitsschritt')+'“. Die Automatik wurde angehalten. Diagnose speichern und erneut versuchen.'
    return {
        'id': job['id'], 'action': job.get('action',''), 'phase':job.get('phase',''),
        'phase_label':job.get('phase_label',''), 'type':type(exc).__name__,
        'message':message, 'technical':technical, 'cancelled':cancelled,
        'recovery':recovery_hint(technical,job.get('phase','')), 
        'traceback':redact(''.join(traceback.format_exception(type(exc),exc,exc.__traceback__)), paths, secrets)[-30000:],
        'logs': [redact(line, paths, secrets) for line in job.get('logs',[])][-120:],
        'note':'Lokale Diagnose ohne Spiel-/Moddateien. Vor dem Weitergeben trotzdem kurz prüfen.',
    }


def recovery_hint(message,phase_key=''):
    """Closed, deterministic recovery catalogue. Never runs downloaded scripts."""
    if 'ARCHIVE_MISMATCH' in message:
        return {'code':'ARCHIVE_LAYOUT_MISMATCH','automatic':False,
                'instruction':'Andere passende Downloads werden weiter übernommen. Diese Datei nicht erzwingen. Fehlende/zusätzliche Pfade und Größen in Diagnose prüfen; bei neuem Download erneut importieren.'}
    if 'START_NOT_READY' in message:
        return {'code':'VERIFY_SELECTED_BUILD','automatic':False,
                'instruction':'Prüfung erneut starten. Veränderte Dateien bleiben unberührt. Erst gewünschte Änderungen sichern, dann über den Installer kontrolliert zurücknehmen/neu installieren.'}
    if any(x in message.lower() for x in ('verbindung','timeout','zeitüberschreitung')):
        return {'code':'RETRY_NETWORK','automatic':False,
                'instruction':'Nach den begrenzten internen Wiederholungen: Verbindung prüfen und erneut fortsetzen. Vollständig geprüfte Zwischenschritte bleiben erhalten.'}
    if any(x in message.lower() for x in ('sha-256','prüfsumme','hash')):
        return {'code':'VERIFY_TOOL_OR_FILE','automatic':False,
                'instruction':'Keine Hashprüfung abschalten. Offizielle Quelle/Version abgleichen; keine fremde EXE oder DLL einsetzen.'}
    return {'code':'SAFE_PAUSE','automatic':False,'instruction':'Aktuellen Schritt und Diagnose prüfen. Unbekannte Konflikte werden nicht selbstständig überschrieben.'}
