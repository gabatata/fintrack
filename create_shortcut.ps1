# create_shortcut.ps1
# Cria um atalho bonito na Area de Trabalho para abrir o FinTrack no navegador
# Execute uma unica vez com: powershell -ExecutionPolicy Bypass -File create_shortcut.ps1

# ── Edite aqui com sua URL ────────────────────────────────────────────────────
$URL = "https://SEU_DOMINIO_OU_IP"
# ─────────────────────────────────────────────────────────────────────────────

$Desktop    = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$Desktop\FinTrack.lnk"

$WshShell   = New-Object -ComObject WScript.Shell
$Shortcut   = $WshShell.CreateShortcut($ShortcutPath)

# Abre a URL no navegador padrao
$Shortcut.TargetPath       = "C:\Windows\System32\rundll32.exe"
$Shortcut.Arguments        = "url.dll,FileProtocolHandler $URL"
$Shortcut.Description      = "FinTrack - Gestao Financeira Pessoal"
$Shortcut.WorkingDirectory = $Desktop

# Usa o icone do Edge/Chrome como padrao
$BrowserIcon = ""
$BrowserPaths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Windows\System32\shell32.dll"
)
foreach ($path in $BrowserPaths) {
    if (Test-Path $path) {
        $BrowserIcon = $path
        break
    }
}
if ($BrowserIcon) {
    $Shortcut.IconLocation = "$BrowserIcon,0"
}

$Shortcut.Save()

Write-Host ""
Write-Host "Atalho criado na Area de Trabalho: FinTrack.lnk"
Write-Host "Clique duas vezes para abrir o FinTrack no navegador."
Write-Host ""
Write-Host "URL configurada: $URL"
Write-Host "Para alterar a URL, edite este script e rode novamente."
