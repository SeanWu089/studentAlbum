$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$chars = @(0x5B66, 0x751F, 0x5C0F, 0x6863, 0x6848)
$name = -join ($chars | ForEach-Object { [char]$_ })
$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop ($name + '.lnk')
$shell = New-Object -ComObject WScript.Shell

# Preserve the ngrok credential from an older portable install before the
# shortcut is repointed to the new folder. This keeps upgrades one-click.
$userConfigDir = Join-Path $env:LOCALAPPDATA 'StudentAlbum'
$userNgrokConfig = Join-Path $userConfigDir 'ngrok.yml'
if ((Test-Path $linkPath) -and -not (Test-Path $userNgrokConfig)) {
    $oldShortcut = $shell.CreateShortcut($linkPath)
    $oldRoot = $oldShortcut.WorkingDirectory
    if ($oldRoot -and ($oldRoot -ne $root)) {
        $oldNgrokConfig = Join-Path $oldRoot 'app\.runtime\ngrok.yml'
        if (Test-Path $oldNgrokConfig) {
            New-Item -ItemType Directory -Path $userConfigDir -Force | Out-Null
            Copy-Item $oldNgrokConfig $userNgrokConfig
        }
    }
}

$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$shortcut.Arguments = '"' + (Join-Path $root 'StudentAlbum.vbs') + '"'
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = (Join-Path $root 'assets\student-album.ico') + ',0'
$shortcut.Description = $name
$shortcut.Save()
Start-Process $linkPath
