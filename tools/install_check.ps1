# Install / upgrade / uninstall check for PaperKnife+ PC 4.0.0 (SPEC R06).
# Runs: 3.2.2 installer /S  ->  4.0.0 installer /S over it  ->  the installed exe's
# --selftest  ->  uninstaller /S.  Prints one line per check; exit 1 on any failure.
# Run it on a machine (or sandbox) with no PaperKnife+ PC installed: it refuses otherwise.
#   powershell -File tools\install_check.ps1 -Old <3.2.2 Setup.exe> -New <4.0.0 Setup.exe>
param(
    [Parameter(Mandatory)][string]$Old,
    [Parameter(Mandatory)][string]$New
)
$ErrorActionPreference = 'Stop'
$dir   = Join-Path $env:LOCALAPPDATA 'PaperKnifePlusPC'
$unkey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PaperKnifePlusPC'
$vkey  = 'HKCU:\Software\potatameister\PaperKnifePlusPC'
$desk  = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PaperKnife+ PC.lnk'
$menu  = Join-Path ([Environment]::GetFolderPath('Programs')) 'PaperKnife+ PC'
$prefs = Join-Path $env:USERPROFILE '.paperknifepluspc\prefs.json'
$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$fails = 0
function Check($name, [bool]$ok, $detail = '') {
    if ($ok) { "ok   $name $detail" } else { "FAIL $name $detail"; $script:fails++ }
}
function Run($exe, $argList) {
    $p = Start-Process -FilePath $exe -ArgumentList $argList -PassThru -Wait
    return $p.ExitCode
}

if (Test-Path $dir) { throw "$dir exists: refusing to run over an existing install" }
$prefsBefore = if (Test-Path $prefs) { (Get-Item $prefs).LastWriteTimeUtc } else { $null }

# 1. the old version
Check '3.2.2 installs'  ((Run $Old '/S') -eq 0)
Check '3.2.2 version'   ((Get-ItemProperty $unkey).DisplayVersion -eq '3.2.2')
$oldOnly = @(Get-ChildItem "$dir\_internal" -Directory | Select-Object -ExpandProperty Name)
Check '3.2.2 has customtkinter' ($oldOnly -contains 'customtkinter')

# 2. the upgrade
Check '4.0.0 installs over it' ((Run $New '/S') -eq 0)
Check '4.0.0 version' ((Get-ItemProperty $unkey).DisplayVersion -eq '4.0.0')
Check 'same folder' ((Get-ItemProperty $vkey).InstallDir -eq $dir) (Get-ItemProperty $vkey).InstallDir
$exe = Join-Path $dir 'PaperKnifePlusPC.exe'
Check 'exe file version 4.0.0' ((Get-Item $exe).VersionInfo.ProductVersion -eq '4.0.0') (Get-Item $exe).VersionInfo.ProductVersion
$left = @('customtkinter', 'tkinterdnd2', 'tcl', 'tk', '_tcl_data', '_tk_data') |
        Where-Object { Test-Path (Join-Path "$dir\_internal" $_) }
Check 'no 3.2.2 toolkit left' ($left.Count -eq 0) ($left -join ', ')
foreach ($f in 'LICENSE', 'THIRD-PARTY-NOTICES.md', 'licenses\Qt-6.12.0\LGPL-3.0.txt', 'licenses\Qt-6.12.0\GPL-3.0.txt') {
    Check "ships $f" (Test-Path (Join-Path $dir $f))
}
Check 'desktop shortcut' (Test-Path $desk)
Check 'start menu entry' (Test-Path $menu)
$size = [math]::Round(((Get-ChildItem $dir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
"info installed size $size MB"

# 3. the installed app checks itself (temporary HOME: the owner's prefs are not read)
$home2 = Join-Path $env:TEMP ('pk-install-home-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $home2 | Out-Null
$report = Join-Path $here 'installed-selftest.txt'
Remove-Item $report -ErrorAction SilentlyContinue
$env:HOME = $home2; $env:USERPROFILE = $home2
$p = Start-Process -FilePath $exe -ArgumentList '--selftest', "`"$report`"" -PassThru
if (-not $p.WaitForExit(180000)) { $p.Kill(); Check 'selftest finished' $false 'timed out' }
else { Check 'selftest passes' ($p.ExitCode -eq 0) "exit $($p.ExitCode); $(Get-Content $report -Tail 1)" }
Remove-Item -Recurse -Force $home2

# 4. the uninstall (_?= makes the call wait until the files are gone)
$env:USERPROFILE = [Environment]::GetFolderPath('UserProfile')
Check 'uninstall' ((Run (Join-Path $dir 'Uninstall.exe') @('/S', "_?=$dir")) -eq 0)
Remove-Item (Join-Path $dir 'Uninstall.exe') -ErrorAction SilentlyContinue   # _?= leaves it
Remove-Item $dir -ErrorAction SilentlyContinue                               # and its folder
Check 'install folder gone' (-not (Test-Path $dir))
Check 'uninstall key gone' (-not (Test-Path $unkey))
Check 'vendor key gone' (-not (Test-Path $vkey))
Check 'desktop shortcut gone' (-not (Test-Path $desk))
Check 'start menu entry gone' (-not (Test-Path $menu))
$prefsAfter = if (Test-Path $prefs) { (Get-Item $prefs).LastWriteTimeUtc } else { $null }
Check "owner's prefs untouched" ($prefsBefore -eq $prefsAfter) "$prefsAfter"
if ($fails) { "FAILED $fails"; exit 1 } else { "ALL PASSED"; exit 0 }
