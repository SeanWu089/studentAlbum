$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$chars = @(0x5B66, 0x751F, 0x5C0F, 0x6863, 0x6848)
$name = -join ($chars | ForEach-Object { [char]$_ })
$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop ($name + '.lnk')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$shortcut.Arguments = '"' + (Join-Path $root 'StudentAlbum.vbs') + '"'
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = (Join-Path $root 'assets\student-album.ico') + ',0'
$shortcut.Description = $name
$shortcut.Save()
Start-Process $linkPath
