[CmdletBinding()]
param(
    [string]$Remote = "bitbucket",
    [string]$Branch = "main",
    [string]$ExpectedUrl = "https://scm.mastercard.int/stash/scm/~e176097/autobench.git"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-GitText {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$GitArgs
    )

    $output = & git @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed: $output"
    }
    return ($output -join "`n").Trim()
}

$repoRoot = Invoke-GitText rev-parse --show-toplevel
Set-Location $repoRoot

$currentBranch = Invoke-GitText branch --show-current
if ([string]::IsNullOrWhiteSpace($currentBranch)) {
    $currentBranch = "(detached HEAD)"
}

Write-Host "Repository: $repoRoot"
Write-Host "Branch:     $currentBranch"

$remoteUrl = & git remote get-url $Remote 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Remote '$Remote' is not configured."
    Write-Host ""
    Write-Host "Add it with:"
    Write-Host "  git remote add $Remote $ExpectedUrl"
    exit 1
}

$remoteUrl = ($remoteUrl -join "`n").Trim()
Write-Host "Remote:     $Remote -> $remoteUrl"

if ($Remote -eq "bitbucket" -and $remoteUrl -ne $ExpectedUrl) {
    Write-Warning "Remote '$Remote' does not match the expected Bitbucket URL."
    Write-Host ""
    Write-Host "Fix it with:"
    Write-Host "  git remote set-url $Remote $ExpectedUrl"
    exit 1
}

$dirty = & git status --short
if ($dirty) {
    Write-Host ""
    Write-Host "Working tree has local changes:"
    $dirty | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host ""
    Write-Host "Working tree is clean."
}

$remoteRef = "refs/remotes/$Remote/$Branch"
& git show-ref --verify --quiet $remoteRef
if ($LASTEXITCODE -eq 0) {
    $ahead = Invoke-GitText rev-list --count "$Remote/$Branch..HEAD"
    $behind = Invoke-GitText rev-list --count "HEAD..$Remote/$Branch"
    Write-Host ""
    Write-Host "Compared with ${Remote}/${Branch}: ahead=$ahead behind=$behind"
} else {
    Write-Host ""
    Write-Warning "No local tracking ref for ${Remote}/${Branch}."
    Write-Host "Run this when you want to inspect remote state:"
    Write-Host "  git fetch $Remote"
}

Write-Host ""
Write-Host "When ready to publish this branch to Bitbucket, run:"
Write-Host "  git push -u $Remote HEAD"
exit 0
