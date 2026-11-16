[CmdletBinding()]
param(
    [ValidateSet('Inspect', 'Start', 'Restart')][string]$Mode = 'Inspect',
    [string]$ExePath,
    [ValidateRange(1024, 65535)][int]$Port = 9333
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Get-DebugTarget {
    try {
        $targets = @(Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/list" -TimeoutSec 1)
        return $targets | Where-Object { $_.url -like '*/micro_aigc/*' } | Select-Object -First 1
    } catch { return $null }
}
function Complete-Result([string]$Status, [string]$Detail = '') {
    [ordered]@{ status = $Status; detail = $Detail; executable = $script:resolvedExe
        endpoint = "http://127.0.0.1:$Port"; mode = $Mode } | ConvertTo-Json -Compress
}

$script:resolvedExe = $null
try {
    if (-not $ExePath) {
        $candidate = Get-Process -Name '超级编导' -ErrorAction SilentlyContinue |
            Where-Object { $_.Path } | Select-Object -First 1
        if ($candidate) { $ExePath = $candidate.Path }
        else {
            $shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) '超级编导.lnk'
            if (Test-Path -LiteralPath $shortcut) {
                $shellLink = New-Object -ComObject WScript.Shell
                $ExePath = $shellLink.CreateShortcut($shortcut).TargetPath
            }
        }
    }
    if (-not $ExePath) { throw 'Cannot find application. Supply -ExePath with its actual executable.' }
    $script:resolvedExe = (Resolve-Path -LiteralPath $ExePath).Path
    if ([IO.Path]::GetExtension($script:resolvedExe) -ne '.exe') { throw 'ExePath must be an existing .exe.' }
    $appProcesses = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $script:resolvedExe })
    $target = Get-DebugTarget
    if ($Mode -eq 'Inspect') {
        $status = if ($target) { 'attach-ready' } elseif ($appProcesses.Count) { 'running-without-generation-target' } else { 'closed' }
        Complete-Result $status
        exit 0
    }
    if ($Mode -eq 'Start' -and $target) { Complete-Result 'attach-ready'; exit 0 }
    if ($appProcesses.Count) {
        if ($Mode -ne 'Restart') { Complete-Result 'restart-required' 'Check current tasks/drafts, then use Restart.'; exit 2 }
        # Only normal window close; never terminate processes or disturb another application.
        $windows = @($appProcesses | Where-Object { $_.MainWindowHandle -ne 0 })
        if (-not $windows.Count) { Complete-Result 'manual-exit-required' 'No accessible normal application window.'; exit 2 }
        foreach ($appWindow in $windows) {
            try {
                if (-not $appWindow.CloseMainWindow()) { throw 'Normal close request was rejected.' }
            } catch {
                Complete-Result 'manual-exit-required' $_.Exception.Message
                exit 2
            }
        }
        $exitDeadline = [DateTime]::UtcNow.AddSeconds(8)
        do {
            $remaining = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $script:resolvedExe })
            if (-not $remaining.Count) { break }
            Start-Sleep -Milliseconds 200
        } while ([DateTime]::UtcNow -lt $exitDeadline)
        if ($remaining.Count) { Complete-Result 'manual-exit-required' 'Application did not close within 8 seconds; no force kill attempted.'; exit 2 }
    }
    # Fail before launching if a different service still owns the chosen port.
    $occupied = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($occupied) { Complete-Result 'port-in-use' 'Use another loopback debugging port.'; exit 2 }
    $previousCompat = $env:__COMPAT_LAYER
    try {
        $env:__COMPAT_LAYER = 'RunAsInvoker'
        # This is the user-requested visible desktop application, not a background helper.
        Start-Process -FilePath $script:resolvedExe -ArgumentList @("--remote-debugging-port=$Port", '--remote-debugging-address=127.0.0.1') | Out-Null
    } finally {
        if ($null -eq $previousCompat) { Remove-Item Env:\__COMPAT_LAYER -ErrorAction SilentlyContinue }
        else { $env:__COMPAT_LAYER = $previousCompat }
    }
    $readyDeadline = [DateTime]::UtcNow.AddSeconds(20)
    do {
        if (Get-DebugTarget) { Complete-Result 'attach-ready'; exit 0 }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $readyDeadline)
    Complete-Result 'open-generation-page' 'Application started. Open AIGC素材生产 and attach; do not launch again.'
    exit 2
} catch {
    Complete-Result 'error' $_.Exception.Message
    exit 1
}
