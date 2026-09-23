# Optional, user-confirmed local Python download. No global install, PATH or registry edits.
# Version and download URL taken from python.org's Windows releases page on 2026-09-23.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root '.runtime'
$url = 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Dieses portable Startpaket benoetigt 64-bit Windows. Python alternativ selbst installieren.' }
Write-Host ''
Write-Host 'Python wird fuer den lokalen Browser-Assistenten benoetigt.'
Write-Host 'Quelle: https://www.python.org (Version 3.13.15, Windows x64)'
Write-Host 'Ziel: .runtime neben README.html. Keine globale Installation.'
Write-Host 'Der Download wird ueber HTTPS geladen. Die Python-EXE wird vor dem Start auf eine gueltige Python-Software-Foundation-Signatur geprueft.'
$answer = Read-Host 'Jetzt herunterladen? [J/N]'
if ($answer -notmatch '^[jJyY]$') { exit 1 }
if (Test-Path -LiteralPath $dest) { throw 'Ordner .runtime existiert bereits. Inhalt zuerst pruefen; er wird nicht automatisch ueberschrieben.' }
$tmp = Join-Path $root ('.runtime-setup-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zip = Join-Path $tmp 'python.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip -TimeoutSec 180
    $out = Join-Path $tmp 'python'
    Expand-Archive -LiteralPath $zip -DestinationPath $out
    $sig = Get-AuthenticodeSignature -LiteralPath (Join-Path $out 'python.exe')
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        throw 'Python-Signatur konnte nicht bestaetigt werden. Nichts wird ausgefuehrt. Python bitte direkt ueber python.org installieren.'
    }
    $sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
    @{
        url=$url; sha256=$sha; downloaded_utc=[DateTime]::UtcNow.ToString('o')
        python_exe_signature=$sig.Status.ToString(); signer=$sig.SignerCertificate.Subject
        note='ZIP hash is a local record, not an independently pinned publisher checksum. Download and Authenticode rely on system TLS/certificate trust.'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'download-record.json') -Encoding UTF8
    Move-Item -LiteralPath $out -Destination $dest
    Write-Host 'Lokale Python-Laufzeit eingerichtet.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'Alternative: Python unter https://www.python.org/downloads/windows/ installieren und STARTEN.cmd erneut oeffnen.'
    exit 1
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
