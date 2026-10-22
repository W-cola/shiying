$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$program = Get-Item -LiteralPath (Join-Path $projectRoot 'dist\ShiYing\拾影.exe')
$iconFile = Get-Item -LiteralPath (Join-Path $program.DirectoryName '拾影.ico')
$desktopFolder = [Environment]::GetFolderPath('DesktopDirectory')
if (-not (Test-Path -LiteralPath $desktopFolder -PathType Container)) {
    throw '未找到当前用户的桌面文件夹。'
}
$shortcutPath = Join-Path $desktopFolder '拾影.lnk'
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $program.FullName
$shortcut.WorkingDirectory = $program.DirectoryName
$shortcut.IconLocation = $iconFile.FullName + ',0'
$shortcut.Description = '拾影 · 视频、图文与原声'
$shortcut.Save()
Write-Output $shortcutPath
