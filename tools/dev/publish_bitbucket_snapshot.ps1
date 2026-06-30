[CmdletBinding()]
param(
    [string]$Remote = "bitbucket",
    [string]$Branch = "main",
    [string]$SourceRef = "main",
    [string]$ExpectedUrl = "https://scm.mastercard.int/stash/scm/~e176097/autobench.git",
    [string]$TokenEnvVar = "BB_TOKEN"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Normalize-RemoteLocation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $trimmed = $Value.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        return ""
    }

    if ($trimmed -match '^[A-Za-z]:[\\/]' -or $trimmed.StartsWith('\') -or $trimmed.StartsWith('/')) {
        try {
            return (Resolve-Path -LiteralPath $trimmed).Path.TrimEnd('\').ToLowerInvariant()
        } catch {
            return $trimmed.Replace('/', '\').TrimEnd('\').ToLowerInvariant()
        }
    }

    return $trimmed.TrimEnd('/').ToLowerInvariant()
}

function Test-AuthFailureMessage {
    param(
        [string]$Message
    )

    $patterns = @(
        "terminal prompts disabled",
        "authentication failed",
        "could not read username",
        "could not read password",
        "http basic: access denied",
        "403",
        "401"
    )

    foreach ($pattern in $patterns) {
        if ($Message -match [regex]::Escape($pattern)) {
            return $true
        }
    }

    return $false
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs,
        [switch]$UseAuth
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    $authEnvName = "AUTOBENCH_GIT_AUTH_HEADER"
    $previousAuthHeader = [Environment]::GetEnvironmentVariable($authEnvName)

    try {
        $gitExe = (Get-Command git).Source
        $argumentList = @()

        if ($UseAuth -and $script:BitbucketToken) {
            [Environment]::SetEnvironmentVariable(
                $authEnvName,
                "Authorization: Bearer $script:BitbucketToken"
            )
            $argumentList += "--config-env=http.extraHeader=$authEnvName"
        }

        $argumentList += $GitArgs
        $process = Start-Process -FilePath $gitExe `
            -ArgumentList $argumentList `
            -NoNewWindow `
            -PassThru `
            -Wait `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        $exitCode = $process.ExitCode
        $stdout = Get-Content -Raw $stdoutPath -ErrorAction SilentlyContinue
        $stderr = Get-Content -Raw $stderrPath -ErrorAction SilentlyContinue
        $text = (@($stdout, $stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "`n"
        $text = $text.Trim()
    } finally {
        if ($null -eq $previousAuthHeader) {
            [Environment]::SetEnvironmentVariable($authEnvName, $null)
        } else {
            [Environment]::SetEnvironmentVariable($authEnvName, $previousAuthHeader)
        }
        Remove-Item $stdoutPath, $stderrPath -ErrorAction SilentlyContinue
    }

    [pscustomobject]@{
        ExitCode = $exitCode
        Output   = $text
    }
}

function Invoke-GitOrThrow {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs,
        [switch]$UseAuth,
        [string]$Operation
    )

    $result = Invoke-Git -GitArgs $GitArgs -UseAuth:$UseAuth
    if ($result.ExitCode -ne 0) {
        $label = if ($Operation) { $Operation } else { "git $($GitArgs -join ' ')" }
        $detail = if ([string]::IsNullOrWhiteSpace($result.Output)) {
            "exit code $($result.ExitCode)"
        } else {
            $result.Output
        }
        throw "$label failed: $detail"
    }

    return $result.Output
}

$script:BitbucketToken = [Environment]::GetEnvironmentVariable($TokenEnvVar)
$originalPromptSetting = [Environment]::GetEnvironmentVariable("GIT_TERMINAL_PROMPT")
$originalBranch = $null
$originalHead = $null
$switchedToDetached = $false

try {
    [Environment]::SetEnvironmentVariable("GIT_TERMINAL_PROMPT", "0")

    $repoRoot = Invoke-GitOrThrow -GitArgs @("rev-parse", "--show-toplevel") -Operation "Resolve repository root"
    Set-Location $repoRoot

    $originalBranch = (Invoke-GitOrThrow -GitArgs @("branch", "--show-current") -Operation "Resolve current branch").Trim()
    $originalHead = Invoke-GitOrThrow -GitArgs @("rev-parse", "HEAD") -Operation "Resolve current HEAD"

    $remoteUrlResult = Invoke-Git -GitArgs @("remote", "get-url", $Remote)
    if ($remoteUrlResult.ExitCode -ne 0) {
        throw "Remote '$Remote' is not configured. Add it with: git remote add $Remote $ExpectedUrl"
    }

    $remoteUrl = $remoteUrlResult.Output.Trim()
    if ((Normalize-RemoteLocation $remoteUrl) -ne (Normalize-RemoteLocation $ExpectedUrl)) {
        throw "Remote '$Remote' does not match the expected deployment URL. Expected '$ExpectedUrl' but found '$remoteUrl'."
    }

    $dirty = Invoke-Git -GitArgs @("status", "--short")
    if (-not [string]::IsNullOrWhiteSpace($dirty.Output)) {
        throw "Working tree must be clean before publishing a deployment snapshot."
    }

    $sourceCommit = Invoke-GitOrThrow -GitArgs @("rev-parse", $SourceRef) -Operation "Resolve source commit"
    $sourceShort = Invoke-GitOrThrow -GitArgs @("rev-parse", "--short", $SourceRef) -Operation "Resolve source short SHA"
    $authorName = Invoke-GitOrThrow -GitArgs @("config", "user.name") -Operation "Resolve git author name"
    $authorEmail = Invoke-GitOrThrow -GitArgs @("config", "user.email") -Operation "Resolve git author email"
    $author = "$authorName <$authorEmail>"

    Invoke-GitOrThrow -GitArgs @("fetch", $Remote, $Branch) -UseAuth -Operation "Fetch $Remote/$Branch"
    $bitbucketParent = Invoke-GitOrThrow -GitArgs @("rev-parse", "$Remote/$Branch") -Operation "Resolve $Remote/$Branch"

    Write-Host "Repository: $repoRoot"
    if ([string]::IsNullOrWhiteSpace($originalBranch)) {
        Write-Host "Starting branch: (detached HEAD)"
    } else {
        Write-Host "Starting branch: $originalBranch"
    }
    Write-Host "Remote URL: $remoteUrl"
    Write-Host "Source commit: $sourceCommit"
    Write-Host "Source short SHA: $sourceShort"
    Write-Host "Bitbucket parent SHA: $bitbucketParent"
    Write-Host "Author: $author"

    Invoke-GitOrThrow -GitArgs @("checkout", "--detach", $SourceRef) -Operation "Detach at $SourceRef"
    $switchedToDetached = $true
    Invoke-GitOrThrow -GitArgs @("reset", "--soft", "$Remote/$Branch") -Operation "Re-parent source tree on $Remote/$Branch"

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    $message = "Deploy snapshot: autobench $SourceRef $sourceShort ($timestamp)"
    $messageFile = [System.IO.Path]::GetTempFileName()
    try {
        Set-Content -LiteralPath $messageFile -Value $message -Encoding utf8
        Invoke-GitOrThrow -GitArgs @("commit", "-F", $messageFile) -Operation "Create deployment snapshot commit"
    } finally {
        Remove-Item $messageFile -ErrorAction SilentlyContinue
    }

    $newSnapshotSha = Invoke-GitOrThrow -GitArgs @("rev-parse", "HEAD") -Operation "Resolve new snapshot SHA"
    Write-Host "New snapshot SHA: $newSnapshotSha"

    $pushResult = Invoke-Git -GitArgs @("push", $Remote, "HEAD:refs/heads/$Branch") -UseAuth
    if ($pushResult.ExitCode -ne 0) {
        throw "Push deployment snapshot failed: $($pushResult.Output)"
    }

    Write-Host "Push result: success"
    if (-not [string]::IsNullOrWhiteSpace($pushResult.Output)) {
        Write-Host $pushResult.Output
    }
    exit 0
} catch {
    $message = $_.Exception.Message
    if (Test-AuthFailureMessage $message) {
        Write-Error "Interactive Bitbucket auth is required. No retry was attempted. Leave a terminal ready for user takeover or set `$env:$TokenEnvVar before re-running."
        exit 1
    }

    if ($message -match "expected deployment URL") {
        Write-Error $message
        exit 1
    }

    Write-Error $message
    exit 1
} finally {
    if ($switchedToDetached) {
        if ([string]::IsNullOrWhiteSpace($originalBranch)) {
            $restoreResult = Invoke-Git -GitArgs @("checkout", "--detach", $originalHead)
        } else {
            $restoreResult = Invoke-Git -GitArgs @("checkout", $originalBranch)
        }

        if ($restoreResult.ExitCode -ne 0 -and -not [string]::IsNullOrWhiteSpace($restoreResult.Output)) {
            Write-Warning "Failed to restore original Git position: $($restoreResult.Output)"
        }
    }

    if ($null -eq $originalPromptSetting) {
        [Environment]::SetEnvironmentVariable("GIT_TERMINAL_PROMPT", $null)
    } else {
        [Environment]::SetEnvironmentVariable("GIT_TERMINAL_PROMPT", $originalPromptSetting)
    }
}
