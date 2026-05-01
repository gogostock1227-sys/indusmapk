$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSCommandPath
$DailyBuild = Join-Path $ProjectDir "daily_build.bat"

if (-not (Test-Path $DailyBuild)) {
    throw "daily_build.bat not found: $DailyBuild"
}

$targetTasks = @(
    @{
        Name = "IndusMapK Daily Build 1530";
        Time = "15:30";
        Description = "IndusMapK daily rebuild - first after-market pass."
    },
    @{
        Name = "IndusMapK Daily Build 1700";
        Time = "17:00";
        Description = "IndusMapK daily rebuild - main complete pass."
    },
    @{
        Name = "IndusMapK Daily Build 2130";
        Time = "21:30";
        Description = "IndusMapK daily rebuild - evening completeness pass."
    }
)

$targetNames = $targetTasks | ForEach-Object { $_.Name }
$dailyBuildFull = (Resolve-Path $DailyBuild).Path

Write-Host "Project dir: $ProjectDir"
Write-Host "Daily build: $dailyBuildFull"
Write-Host ""

# Disable old schedules that point to this project's daily_build.bat, so a
# previous 14:30 task does not keep running in addition to the three new tasks.
$oldTasks = Get-ScheduledTask | Where-Object {
    $task = $_
    $pointsToThisBuild = $false
    foreach ($action in $task.Actions) {
        $execute = [string]$action.Execute
        $arguments = [string]$action.Arguments
        if ($execute -like "*daily_build.bat*" -or
            $arguments -like "*daily_build.bat*" -or
            $execute -eq $dailyBuildFull -or
            $arguments -like "*$dailyBuildFull*") {
            $pointsToThisBuild = $true
            break
        }
    }
    $pointsToThisBuild -and ($targetNames -notcontains $task.TaskName)
}

foreach ($task in $oldTasks) {
    Write-Host "Disabling old task: $($task.TaskPath)$($task.TaskName)"
    try {
        Disable-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath | Out-Null
    } catch {
        Write-Warning "Could not disable old task '$($task.TaskName)'. Run this script as Administrator, or disable it manually."
    }
}

$activeOldTimes = @{}
foreach ($task in $oldTasks) {
    try {
        $latest = Get-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath
        if ($latest.State -eq "Disabled") {
            continue
        }
        foreach ($trigger in $latest.Triggers) {
            if ($trigger.StartBoundary) {
                $timeKey = ([datetime]$trigger.StartBoundary).ToString("HH:mm")
                if (-not $activeOldTimes.ContainsKey($timeKey)) {
                    $activeOldTimes[$timeKey] = @()
                }
                $activeOldTimes[$timeKey] += $latest.TaskName
            }
        }
    } catch {
        Write-Warning "Could not inspect old task '$($task.TaskName)'."
    }
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

foreach ($taskDef in $targetTasks) {
    if ($activeOldTimes.ContainsKey($taskDef.Time)) {
        Write-Host "Existing active task already covers $($taskDef.Time): $($activeOldTimes[$taskDef.Time] -join ', ')"
        Write-Host "Skipping duplicate target: $($taskDef.Name)"
        continue
    }

    $at = [datetime]::Today.Add([timespan]::Parse($taskDef.Time))
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
    $action = New-ScheduledTaskAction `
        -Execute $dailyBuildFull `
        -Argument "quiet" `
        -WorkingDirectory $ProjectDir

    Register-ScheduledTask `
        -TaskName $taskDef.Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $taskDef.Description `
        -Force | Out-Null

    Write-Host "Registered: $($taskDef.Name) @ $($taskDef.Time)"
}

Write-Host ""
Write-Host "Current schedules:"
$trackedNames = @()
$trackedNames += $targetNames
$trackedNames += ($oldTasks | ForEach-Object { $_.TaskName })
$trackedNames = $trackedNames | Sort-Object -Unique

foreach ($name in $trackedNames) {
    try {
        $task = Get-ScheduledTask -TaskName $name
        $info = Get-ScheduledTaskInfo -TaskName $name -TaskPath $task.TaskPath
        $nextRun = if ($info.NextRunTime) { $info.NextRunTime } else { "not calculated yet" }
        Write-Host ("- {0} | State={1} | NextRun={2}" -f $task.TaskName, $task.State, $nextRun)
    } catch {
        # The 17:00 target may be skipped when an existing old task already
        # covers that same time. In that case there is nothing to print here.
    }
}

Write-Host ""
Write-Host "Done. All three schedules run daily_build.bat quiet."
