param(
    [switch]$Confirmed,
    [int]$MaximumDeletes = 5000,
    [int]$RecoveryReloads = 3
)

if (-not $Confirmed) {
    throw 'Explicit confirmation is required. Run again with -Confirmed only after the user confirms deleting every work.'
}

$lockPath = Join-Path ([System.IO.Path]::GetTempPath()) 'codex-douyin-delete-all-works.lock'
try {
    $lockStream = [System.IO.File]::Open(
        $lockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch {
    throw 'Another Douyin delete-all process is already running.'
}

Add-Type -AssemblyName UIAutomationClient

$ErrorActionPreference = 'Stop'
$creatorCenterTitle = -join ([char[]](0x6296, 0x97F3, 0x521B, 0x4F5C, 0x8005, 0x4E2D, 0x5FC3))
$workPrefix = -join ([char[]](0x4F5C, 0x54C1))
$deleteName = -join ([char[]](0x5220, 0x9664, 0x4F5C, 0x54C1))
$confirmName = -join ([char[]](0x786E, 0x5B9A))
$dialogName = -join ([char[]](0x786E, 0x5B9A, 0x8981, 0x79FB, 0x9664, 0x6B64, 0x4F5C, 0x54C1, 0x5417))
$reloadName = -join ([char[]](0x91CD, 0x65B0, 0x52A0, 0x8F7D))
$deleted = 0

function Get-ChromeRoot {
    $chrome = Get-Process chrome |
        Where-Object {
            $_.MainWindowHandle -ne 0 -and
            $_.MainWindowTitle -like "*$creatorCenterTitle*"
        } |
        Select-Object -First 1

    if (-not $chrome) {
        throw 'Douyin Creator Center Chrome window was not found.'
    }

    [System.Windows.Automation.AutomationElement]::FromHandle($chrome.MainWindowHandle)
}

function Find-ByName {
    param([string]$Name)

    $root = Get-ChromeRoot
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $Name
    )
    $root.FindFirst(
        [System.Windows.Automation.TreeScope]::Descendants,
        $condition
    )
}

function Get-WorkCount {
    $root = Get-ChromeRoot
    $buttonCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button
    )
    $buttons = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        $buttonCondition
    )

    foreach ($button in $buttons) {
        $countPattern = '^' + [regex]::Escape($workPrefix) + ' \((\d+)\)$'
        if ($button.Current.Name -match $countPattern) {
            return [int]$Matches[1]
        }
    }

    return $null
}

function Invoke-Element {
    param([System.Windows.Automation.AutomationElement]$Element)

    $pattern = $Element.GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    )
    $pattern.Invoke()
}

function Get-DeleteState {
    $deleteText = Find-ByName -Name $deleteName
    if (-not $deleteText) {
        return $null
    }

    $walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
    $candidate = $walker.GetParent($deleteText)
    $invokeElement = $null
    $cardElement = $null
    for ($level = 0; $level -lt 8 -and $candidate; $level++) {
        $patternObject = $null
        if (-not $invokeElement -and $candidate.TryGetCurrentPattern(
            [System.Windows.Automation.InvokePattern]::Pattern,
            [ref]$patternObject
        )) {
            $invokeElement = $candidate
        }
        if ($candidate.Current.ClassName -like '*video-card-*') {
            $cardElement = $candidate
            break
        }
        $candidate = $walker.GetParent($candidate)
    }

    if (-not $invokeElement -or -not $cardElement) {
        throw 'Delete control or work card was not found.'
    }

    $textCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Text
    )
    $texts = $cardElement.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        $textCondition
    )
    $textNames = foreach ($text in $texts) {
        if ($text.Current.Name) {
            $text.Current.Name
        }
    }

    [PSCustomObject]@{
        InvokeElement = $invokeElement
        Fingerprint = $textNames -join '|'
        RuntimeId = $deleteText.GetRuntimeId() -join '.'
    }
}

function Wait-ForElement {
    param(
        [string]$Name,
        [int]$TimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $element = Find-ByName -Name $Name
        if ($element) {
            return $element
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)

    return $null
}

function Wait-ForRefresh {
    param(
        [int]$BeforeCount,
        [string]$BeforeFingerprint,
        [string]$BeforeRuntimeId,
        [int]$TimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $count = Get-WorkCount
            $dialog = Find-ByName -Name $dialogName
            $state = Get-DeleteState
            if (-not $dialog -and $count -eq 0 -and -not $state) {
                return [PSCustomObject]@{ Count = 0; State = $null }
            }
            if (-not $dialog -and $state) {
                $countChanged = $null -ne $count -and $count -lt $BeforeCount
                $cardChanged = $state.Fingerprint -ne $BeforeFingerprint
                if ($countChanged -or $cardChanged) {
                    return [PSCustomObject]@{ Count = $count; State = $state }
                }
            }
        } catch {
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    return $null
}

function Recover-WorkList {
    param(
        [string]$BeforeRuntimeId,
        [int]$Attempts
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $reload = Find-ByName -Name $reloadName
        if (-not $reload) {
            throw 'Chrome reload control was not found.'
        }
        Invoke-Element -Element $reload

        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            try {
                $dialog = Find-ByName -Name $dialogName
                $state = Get-DeleteState
                $count = Get-WorkCount
                if (-not $dialog -and $count -eq 0 -and -not $state) {
                    return [PSCustomObject]@{ Count = 0; State = $null; Attempt = $attempt }
                }
                if (
                    -not $dialog -and
                    $state -and
                    $state.RuntimeId -ne $BeforeRuntimeId
                ) {
                    return [PSCustomObject]@{ Count = $count; State = $state; Attempt = $attempt }
                }
            } catch {
            }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $deadline)
    }

    return $null
}

$initialCount = Get-WorkCount
if ($null -eq $initialCount) {
    throw 'The current work count could not be read.'
}

Write-Output "START count=$initialCount"

while ($true) {
    $beforeCount = Get-WorkCount
    if ($null -eq $beforeCount) {
        throw 'The work count disappeared before deletion.'
    }
    if ($beforeCount -eq 0) {
        break
    }
    if ($deleted -ge $MaximumDeletes) {
        throw "Safety limit reached with $beforeCount works remaining."
    }

    $beforeState = Get-DeleteState
    if (-not $beforeState) {
        if ($beforeCount -eq 0) {
            break
        }
        throw "Delete control was not found with $beforeCount works reported."
    }
    Invoke-Element -Element $beforeState.InvokeElement

    $dialog = Wait-ForElement -Name $dialogName -TimeoutSeconds 5
    if (-not $dialog) {
        throw "Delete confirmation dialog did not appear at count $beforeCount."
    }

    $confirm = Wait-ForElement -Name $confirmName -TimeoutSeconds 2
    if (-not $confirm) {
        throw "Confirm button was not found at count $beforeCount."
    }

    Invoke-Element -Element $confirm

    $refresh = Wait-ForRefresh -BeforeCount $beforeCount -BeforeFingerprint $beforeState.Fingerprint -BeforeRuntimeId $beforeState.RuntimeId -TimeoutSeconds 30
    if ($null -eq $refresh) {
        $recovery = Recover-WorkList -BeforeRuntimeId $beforeState.RuntimeId -Attempts $RecoveryReloads
        if ($null -eq $recovery) {
            $actualCount = Get-WorkCount
            throw "The work list did not recover after $RecoveryReloads reloads; current count is $actualCount."
        }
        Write-Output "RECOVERED reload_attempt=$($recovery.Attempt) remaining=$($recovery.Count)"
        continue
    }

    $deleted++
    if ($deleted -eq 1 -or $deleted % 10 -eq 0 -or $refresh.Count -eq 0) {
        Write-Output "PROGRESS deleted=$deleted remaining=$($refresh.Count)"
    }
}

$finalCount = Get-WorkCount
if ($finalCount -ne 0) {
    throw "Final verification failed; count is $finalCount."
}

Write-Output "COMPLETE deleted=$deleted remaining=0"
