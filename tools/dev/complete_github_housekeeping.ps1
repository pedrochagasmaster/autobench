<#
.SYNOPSIS
Completes the GitHub work deferred while the corporate GitHub posting posture is blocked.

.DESCRIPTION
Plan mode is the default and performs local safety checks without changing GitHub.
Pass -Execute only after GitHub posting access is restored.

Execution is intentionally ordered:
1. Verify the repository, local commits, GitHub authentication, and remote main.
2. Push the three preserved local branches and create or reuse their pull requests.
3. Delete only the fixed set of merged-PR heads plus one exact no-PR head
   whose unique history is preserved in a local archive branch.
4. Verify every pushed and deleted ref and confirm that open-PR branches still exist.

The script never targets Bitbucket, merges pull requests, changes branch protection,
creates tags, or deploys.

.EXAMPLE
.\tools\dev\complete_github_housekeeping.ps1

.EXAMPLE
.\tools\dev\complete_github_housekeeping.ps1 -Execute
#>

[CmdletBinding()]
param(
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoSlug = "pedrochagasmaster/autobench"
$remote = "origin"
$expectedRemoteUrl = "https://github.com/pedrochagasmaster/autobench.git"
$expectedMainSha = "0dd0c6619affde33b34da23ecb0ea1c999ebd087"
$runbookBranch = "codex/github-housekeeping-runbook"

$publishBranches = @(
    [pscustomobject]@{
        Name        = "codex/getnet-public-api-contract"
        ExpectedSha = "2975abbbcc6f90f63d4b8288f906715c227b1308"
        Title       = "test: protect governed pipeline public API surface"
        Body        = @"
## Summary

- document the privacy-rule and column-normalization APIs used by governed pipelines
- protect those APIs with import, signature, behavior, and return-type tests

## Validation

- ``py -m pytest tests/test_public_api.py``: 8 passed
- ``py -m pytest -n 4 --dist loadfile``: 545 passed, 36 skipped

## Release risk

Low. This change adds compatibility tests and documentation; it does not change runtime behavior or privacy enforcement.
"@
    }
    [pscustomobject]@{
        Name        = "codex/presets-guide-pt-br"
        ExpectedSha = "740a0b0d432db910cb19595972003d596c11596a"
        Title       = "docs: add Portuguese preset configuration guide"
        Body        = @"
## Summary

- add a comprehensive Portuguese guide for all six Autobench presets
- explain configuration precedence and the behavioral effects of manual settings
- link the guide from the README

## Validation

- six preset names, 11 YAML examples, README link, and whitespace checks passed
- ``py -m pytest -n 4 --dist loadfile``: 542 passed, 36 skipped

## Release risk

Low. Documentation-only change; no runtime or privacy-enforcement behavior changes.
"@
    }
    [pscustomobject]@{
        Name        = $runbookBranch
        ExpectedSha = $null
        Title       = "chore: add deferred GitHub housekeeping runbook"
        Body        = @"
## Summary

- add a guarded, idempotent PowerShell runbook for deferred GitHub publication
- publish preserved branches before deleting 40 merged-PR heads and one locally archived no-PR head
- verify exact refs and fail closed on changed main, authentication, or branch state

## Validation

- PowerShell AST parsing passed
- plan-mode safety checks passed
- ``py -m pytest -n 4 --dist loadfile``: 542 passed, 36 skipped

## Release risk

Low. Developer tooling only. The script defaults to non-mutating plan mode and requires explicit ``-Execute``.
"@
    }
)

$mergedBranchHeads = @(
    "codex/bump-edge-deploy-1.5.3",
    "codex/bump-edge-deploy-core-1.5.1",
    "codex/bump-edge-deploy-core-1.5.2",
    "codex/bump-edge-deploy-core-v1.4.0",
    "codex/e2e-no-deps-20260708-163103",
    "codex/fix-windows-telemetry-validation",
    "codex/new_deployment_workflow",
    "codex/release-gate-wrapping-fix",
    "codex/resolve-active-bundle-path",
    "codex/robustness-hardening-followthrough",
    "codex/shared-global-runtime",
    "cursor/add-thermo-nuclear-review-skill-58f3",
    "cursor/audit-complement-9ff6",
    "cursor/audit-remediation-8d5d",
    "cursor/audit-remediation-consolidation-7963",
    "cursor/audit-remediation-plan-3937",
    "cursor/autobench-branded-pptx-3d19",
    "cursor/de-slop-all-phases-0413",
    "cursor/de-slop-remediation-plan-30b0",
    "cursor/deslop-audit-doc-90cc",
    "cursor/deslop-e2e-c5b9",
    "cursor/domain-truth-refactor-all-phases-6ee4",
    "cursor/env-setup-9acf",
    "cursor/feature-user-stories-audit-6fa6",
    "cursor/fix-cloud-install-58f3",
    "cursor/fix-ruff-tuple-import-04ba",
    "cursor/install-mattpocock-skills-96fe",
    "cursor/lazy-dev-cleanup-33f8",
    "cursor/lean-memory-mode-e42a",
    "cursor/manual-testing-fix-csv-validator-7ead",
    "cursor/migrate-skills-to-cli-58f3",
    "cursor/offline-telemetry-abe3",
    "cursor/onboarding-input-table-example-892d",
    "cursor/production-readiness-audit-d643",
    "cursor/production-readiness-impl-9284",
    "cursor/production-readiness-roadmap-8094",
    "cursor/setup-dev-environment-8472",
    "cursor/simplify-onboarding-html-8a5f",
    "cursor/tui-production-polish-1acb",
    "feat/privacy-stress-hardening"
)

$archivedNoPrHead = [pscustomobject]@{
    Name        = "cursor/pr-consolidation-decisions-f033"
    ExpectedSha = "69b2ad8dd0978cdb682d0c173fed94e484aec1a3"
    ArchiveRef  = "archive/cursor-pr-consolidation-decisions-f033"
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Native tools commonly write progress and transport diagnostics to
        # stderr. Capture those messages and decide from the exit code plus
        # explicit remote verification instead of allowing PowerShell to turn
        # stderr into a terminating ErrorRecord.
        $ErrorActionPreference = "Continue"
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    [pscustomobject]@{
        ExitCode = $exitCode
        Output   = (@($output) -join "`n").Trim()
    }
}

function Invoke-NativeOrThrow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Operation
    )

    $result = Invoke-Native -FilePath $FilePath -Arguments $Arguments
    if ($result.ExitCode -ne 0) {
        $detail = if ([string]::IsNullOrWhiteSpace($result.Output)) {
            "exit code $($result.ExitCode)"
        } else {
            $result.Output
        }
        throw "${Operation} failed: $detail"
    }
    return $result.Output
}

function Resolve-LocalSha {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Ref
    )

    return (Invoke-NativeOrThrow -FilePath "git" -Arguments @("rev-parse", $Ref) -Operation "Resolve local ref '$Ref'").Trim()
}

function Get-RemoteHeads {
    $output = Invoke-NativeOrThrow -FilePath "git" -Arguments @("ls-remote", "--heads", $remote) -Operation "Read GitHub branch heads"
    $heads = @{}
    foreach ($line in @($output -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $parts = $line -split "`t", 2
        if ($parts.Count -ne 2 -or -not $parts[1].StartsWith("refs/heads/")) {
            throw "Unexpected ls-remote output: $line"
        }
        $heads[$parts[1].Substring(11)] = $parts[0]
    }
    return $heads
}

function Assert-LocalPreconditions {
    $repoRoot = (Invoke-NativeOrThrow -FilePath "git" -Arguments @("rev-parse", "--show-toplevel") -Operation "Resolve repository root").Trim()
    Set-Location $repoRoot

    $remoteUrl = (Invoke-NativeOrThrow -FilePath "git" -Arguments @("remote", "get-url", $remote) -Operation "Resolve GitHub remote").Trim()
    if ($remoteUrl -ne $expectedRemoteUrl) {
        throw "Remote '$remote' must be '$expectedRemoteUrl', found '$remoteUrl'."
    }

    $dirty = Invoke-Native -FilePath "git" -Arguments @("status", "--porcelain")
    if (-not [string]::IsNullOrWhiteSpace($dirty.Output)) {
        throw "Working tree must be clean before running GitHub housekeeping: $($dirty.Output)"
    }

    $localMain = Resolve-LocalSha -Ref "main"
    if ($localMain -ne $expectedMainSha) {
        throw "Local main changed. Expected $expectedMainSha, found $localMain. Rebase and revalidate the queued branches before updating this runbook."
    }

    foreach ($item in $publishBranches) {
        $localSha = Resolve-LocalSha -Ref $item.Name
        if ($null -ne $item.ExpectedSha -and $localSha -ne $item.ExpectedSha) {
            throw "Branch '$($item.Name)' changed. Expected $($item.ExpectedSha), found $localSha."
        }
        if ($item.Name -eq $runbookBranch) {
            $ancestor = Invoke-Native -FilePath "git" -Arguments @("merge-base", "--is-ancestor", $expectedMainSha, $localSha)
            if ($ancestor.ExitCode -ne 0) {
                throw "Runbook branch '$runbookBranch' is not based on expected main $expectedMainSha."
            }
        }
    }

    $archiveSha = Resolve-LocalSha -Ref $archivedNoPrHead.ArchiveRef
    if ($archiveSha -ne $archivedNoPrHead.ExpectedSha) {
        throw "Archive '$($archivedNoPrHead.ArchiveRef)' changed. Expected $($archivedNoPrHead.ExpectedSha), found $archiveSha."
    }

    Write-Host "Repository:       $repoRoot"
    Write-Host "GitHub remote:    $remoteUrl"
    Write-Host "Expected main:    $expectedMainSha"
    Write-Host "Branches to push: $($publishBranches.Count)"
    $publishBranches | ForEach-Object { Write-Host "  $($_.Name)" }
    Write-Host "Merged heads to delete if still present: $($mergedBranchHeads.Count)"
    Write-Host "Archived no-PR head to delete if still present: $($archivedNoPrHead.Name)"
}

function Assert-GitHubPosture {
    if ($null -eq (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI 'gh' is required."
    }

    Invoke-NativeOrThrow -FilePath "gh" -Arguments @("auth", "status", "--hostname", "github.com") -Operation "Verify GitHub authentication" | Out-Null
    $fullName = (Invoke-NativeOrThrow -FilePath "gh" -Arguments @("api", "repos/$repoSlug", "--jq", ".full_name") -Operation "Verify GitHub API posture").Trim()
    if ($fullName -ne $repoSlug) {
        throw "GitHub API resolved unexpected repository '$fullName'."
    }

    $remoteHeads = Get-RemoteHeads
    if (-not $remoteHeads.ContainsKey("main")) {
        throw "GitHub main is missing."
    }
    if ($remoteHeads["main"] -ne $expectedMainSha) {
        throw "GitHub main changed. Expected $expectedMainSha, found $($remoteHeads['main']). Rebase and revalidate before execution."
    }
}

function Get-AllPullRequests {
    $json = Invoke-NativeOrThrow -FilePath "gh" -Arguments @(
        "pr", "list",
        "--repo", $repoSlug,
        "--state", "all",
        "--limit", "200",
        "--json", "number,headRefName,baseRefName,state,mergedAt,url"
    ) -Operation "Read GitHub pull requests"

    # Windows PowerShell can emit a JSON array from ConvertFrom-Json as one
    # pipeline object. Enumerate it explicitly so downstream Where-Object
    # filters evaluate one PR at a time instead of matching the whole array.
    $parsed = $json | ConvertFrom-Json
    foreach ($pullRequest in @($parsed)) {
        Write-Output $pullRequest
    }
}

function Push-BranchVerified {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Branch,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedSha
    )

    Write-Host "Pushing $Branch at $ExpectedSha"
    $push = Invoke-Native -FilePath "git" -Arguments @("push", $remote, "${Branch}:refs/heads/$Branch")
    $remoteHeads = Get-RemoteHeads
    $actualSha = if ($remoteHeads.ContainsKey($Branch)) { $remoteHeads[$Branch] } else { $null }

    if ($actualSha -eq $ExpectedSha) {
        if ($push.ExitCode -ne 0) {
            Write-Warning "Push reported an error, but GitHub verification confirms the expected SHA."
        }
        return
    }

    $detail = if ([string]::IsNullOrWhiteSpace($push.Output)) { "exit code $($push.ExitCode)" } else { $push.Output }
    throw "Push verification failed for '$Branch'. Expected '$ExpectedSha', found '$actualSha'. Push output: $detail"
}

function Ensure-PullRequest {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$BranchSpec
    )

    $matches = @(Get-AllPullRequests | Where-Object { $_.headRefName -eq $BranchSpec.Name })
    $open = @($matches | Where-Object { $_.state -eq "OPEN" })
    if ($open.Count -eq 1) {
        if ($open[0].baseRefName -ne "main") {
            throw "Existing PR for '$($BranchSpec.Name)' targets '$($open[0].baseRefName)', not main."
        }
        Write-Host "Reusing PR: $($open[0].url)"
        return $open[0].url
    }
    if ($open.Count -gt 1) {
        throw "Multiple open PRs found for '$($BranchSpec.Name)'."
    }
    if ($matches.Count -gt 0) {
        throw "A closed or merged PR already uses head '$($BranchSpec.Name)'; refusing to create an ambiguous replacement."
    }

    $bodyPath = [System.IO.Path]::GetTempFileName()
    try {
        Set-Content -LiteralPath $bodyPath -Value $BranchSpec.Body -Encoding utf8
        $url = (Invoke-NativeOrThrow -FilePath "gh" -Arguments @(
            "pr", "create",
            "--repo", $repoSlug,
            "--base", "main",
            "--head", $BranchSpec.Name,
            "--title", $BranchSpec.Title,
            "--body-file", $bodyPath
        ) -Operation "Create PR for '$($BranchSpec.Name)'").Trim()
    } finally {
        Remove-Item -LiteralPath $bodyPath -ErrorAction SilentlyContinue
    }

    $verified = @(Get-AllPullRequests | Where-Object {
        $_.headRefName -eq $BranchSpec.Name -and
        $_.baseRefName -eq "main" -and
        $_.state -eq "OPEN"
    })
    if ($verified.Count -ne 1) {
        throw "PR creation for '$($BranchSpec.Name)' could not be verified."
    }
    Write-Host "Created PR: $($verified[0].url)"
    return $verified[0].url
}

function Remove-ApprovedBranchHeads {
    $pullRequests = Get-AllPullRequests
    $mergedHeads = @($pullRequests | Where-Object { $_.state -eq "MERGED" } | ForEach-Object headRefName | Sort-Object -Unique)
    $openHeads = @($pullRequests | Where-Object { $_.state -eq "OPEN" } | ForEach-Object headRefName | Sort-Object -Unique)
    $beforeHeads = Get-RemoteHeads
    $openHeadsPresentBefore = @($openHeads | Where-Object { $beforeHeads.ContainsKey($_) })

    $noPrMatches = @($pullRequests | Where-Object { $_.headRefName -eq $archivedNoPrHead.Name })
    if ($noPrMatches.Count -gt 0) {
        throw "Archived deletion target '$($archivedNoPrHead.Name)' now has a PR record; review it before deletion."
    }
    $archiveSha = Resolve-LocalSha -Ref $archivedNoPrHead.ArchiveRef
    if ($archiveSha -ne $archivedNoPrHead.ExpectedSha) {
        throw "Local archive '$($archivedNoPrHead.ArchiveRef)' no longer preserves expected SHA $($archivedNoPrHead.ExpectedSha)."
    }
    if ($beforeHeads.ContainsKey($archivedNoPrHead.Name) -and
        $beforeHeads[$archivedNoPrHead.Name] -ne $archivedNoPrHead.ExpectedSha) {
        throw "Archived deletion target '$($archivedNoPrHead.Name)' changed on GitHub. Expected $($archivedNoPrHead.ExpectedSha), found $($beforeHeads[$archivedNoPrHead.Name])."
    }

    $approvedDeletionHeads = @($mergedBranchHeads) + @($archivedNoPrHead.Name)
    foreach ($branch in $approvedDeletionHeads) {
        if ($openHeads -contains $branch) {
            throw "Approved deletion target '$branch' now has an open PR."
        }
        if ($branch -ne $archivedNoPrHead.Name -and $mergedHeads -notcontains $branch) {
            throw "Approved deletion target '$branch' no longer has a merged PR record."
        }
        if (-not $beforeHeads.ContainsKey($branch)) {
            Write-Host "Already absent: $branch"
            continue
        }

        Write-Host "Deleting approved branch: $branch"
        $encodedBranch = [System.Uri]::EscapeDataString($branch)
        $delete = Invoke-Native -FilePath "gh" -Arguments @(
            "api", "--method", "DELETE",
            "repos/$repoSlug/git/refs/heads/$encodedBranch"
        )

        $afterDelete = Get-RemoteHeads
        if ($afterDelete.ContainsKey($branch)) {
            $detail = if ([string]::IsNullOrWhiteSpace($delete.Output)) { "exit code $($delete.ExitCode)" } else { $delete.Output }
            throw "Deletion of '$branch' was not verified. GitHub response: $detail"
        }
        if ($delete.ExitCode -ne 0) {
            Write-Warning "Deletion reported an error, but GitHub verification confirms '$branch' is absent."
        }
    }

    Invoke-NativeOrThrow -FilePath "git" -Arguments @("fetch", "--prune", $remote) -Operation "Prune local GitHub tracking refs" | Out-Null

    $finalHeads = Get-RemoteHeads
    $remaining = @($approvedDeletionHeads | Where-Object { $finalHeads.ContainsKey($_) })
    if ($remaining.Count -gt 0) {
        throw "Merged branch cleanup incomplete: $($remaining -join ', ')"
    }
    $missingOpenHeads = @($openHeadsPresentBefore | Where-Object { -not $finalHeads.ContainsKey($_) })
    if ($missingOpenHeads.Count -gt 0) {
        throw "An open-PR branch disappeared during cleanup: $($missingOpenHeads -join ', ')"
    }
    if ($finalHeads["main"] -ne $expectedMainSha) {
        throw "GitHub main changed during housekeeping."
    }
}

Assert-LocalPreconditions

if (-not $Execute) {
    Write-Host ""
    Write-Host "PLAN ONLY - no GitHub changes were made."
    Write-Host "When GitHub posting posture is restored, run:"
    Write-Host "  .\tools\dev\complete_github_housekeeping.ps1 -Execute"
    exit 0
}

Write-Host ""
Write-Host "EXECUTION MODE"
Assert-GitHubPosture

$pullRequestUrls = @()
foreach ($item in $publishBranches) {
    $localSha = Resolve-LocalSha -Ref $item.Name
    Push-BranchVerified -Branch $item.Name -ExpectedSha $localSha
    $pullRequestUrls += Ensure-PullRequest -BranchSpec $item
}

Remove-ApprovedBranchHeads

Write-Host ""
Write-Host "GitHub housekeeping completed and verified."
Write-Host "Pull requests:"
$pullRequestUrls | ForEach-Object { Write-Host "  $_" }
Write-Host "Deleted approved branch heads: $($mergedBranchHeads.Count + 1)"
