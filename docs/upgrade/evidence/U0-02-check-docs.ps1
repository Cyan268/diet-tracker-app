# Read-only checks for the U0-02 documentation deliverables.
# Run from any directory: pwsh -File docs/upgrade/evidence/U0-02-check-docs.ps1
param(
    [string]$RepositoryRoot = (Join-Path $PSScriptRoot '../../..')
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$errors = [System.Collections.Generic.List[string]]::new()
$adrNames = @(
    'ADR-009-single-vps-and-worker.md',
    'ADR-010-authoritative-draft-confirmation.md',
    'ADR-011-log-unit-of-work.md',
    'ADR-012-food-and-log-identity.md',
    'ADR-013-durable-analysis-jobs.md',
    'ADR-014-ordered-sync-and-snapshots.md'
)
$headings = @('背景', '决策', '不选方案', '代价', '兼容策略', '验收测试')
$testIds = [System.Collections.Generic.List[string]]::new()
$files = [System.Collections.Generic.List[string]]::new()

foreach ($name in $adrNames) {
    $relative = "docs/decisions/$name"
    $files.Add($relative)
    $content = Get-Content -LiteralPath (Join-Path $root $relative) -Raw -Encoding utf8
    foreach ($heading in $headings) {
        if ($content -notmatch "(?m)^## $heading\r?$") {
            $errors.Add("Missing heading '$heading': $relative")
        }
    }
    if ($content -notmatch 'Accepted for implementation') {
        $errors.Add("Missing implementation-pending status: $relative")
    }
    $number = [regex]::Match($name, 'ADR-(\d{3})').Groups[1].Value
    $ids = [regex]::Matches($content, '(?m)^\| (T\d{3}-\d{2})\s*\|')
    if ($ids.Count -eq 0) { $errors.Add("Missing acceptance rows: $relative") }
    foreach ($id in $ids) {
        $value = $id.Groups[1].Value
        $testIds.Add($value)
        if (-not $value.StartsWith("T$number-")) {
            $errors.Add("Wrong acceptance prefix: $value in $relative")
        }
    }
}

$duplicates = @($testIds | Group-Object | Where-Object Count -gt 1)
if ($duplicates.Count -gt 0) { $errors.Add('Duplicate acceptance IDs') }
if ($testIds.Count -ne 41) { $errors.Add("Expected 41 acceptance rows; found $($testIds.Count)") }

$allAdrNumbers = Get-ChildItem -LiteralPath (Join-Path $root 'docs/decisions') -Filter 'ADR-*.md' |
    ForEach-Object { [regex]::Match($_.Name, '^ADR-(\d+)').Groups[1].Value }
if (@($allAdrNumbers | Group-Object | Where-Object Count -gt 1).Count -gt 0) {
    $errors.Add('Duplicate ADR file numbers')
}

foreach ($relative in @(
    'docs/upgrade/tasks/U0-02.md', 'README.md', 'docs/ARCHITECTURE.md',
    'docs/ROADMAP.md', 'docs/INTERVIEW_QA.md', 'docs/LEARNING_LOG.md',
    'docs/UPGRADE_DEVELOPMENT_PLAN.md'
)) { $files.Add($relative) }

$localLinks = 0
foreach ($relative in $files) {
    $path = Join-Path $root $relative
    $content = Get-Content -LiteralPath $path -Raw -Encoding utf8
    foreach ($match in [regex]::Matches($content, '(?<!!)\[[^\]\r\n]+\]\(([^)\r\n]+)\)')) {
        $target = $match.Groups[1].Value.Trim('<', '>')
        if ($target -match '^(https?://|mailto:|#)') { continue }
        # This checks file targets, not Markdown heading slug generation.
        $target = [uri]::UnescapeDataString(($target -split '#', 2)[0])
        $resolved = [IO.Path]::GetFullPath((Join-Path (Split-Path $path -Parent) $target))
        $localLinks++
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            $errors.Add("Broken local file link: $relative -> $target")
        }
    }
}

Push-Location $root
try {
    $sha = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git rev-parse failed' }
    $status = @(git -c core.quotepath=false status --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw 'git status failed' }
    foreach ($line in $status) {
        $path = $line.Substring(3).Trim('"')
        if ($path -ne 'README.md' -and -not $path.StartsWith('docs/')) {
            $errors.Add("Non-document worktree change: $path")
        }
    }
    git diff --exit-code -- app src backend __tests__ scripts .github Dockerfile.production compose.yaml render.yaml package.json package-lock.json
    $businessDiffExitCode = $LASTEXITCODE
    if ($businessDiffExitCode -ne 0) { $errors.Add('Business/config tracked diff is not empty') }
} finally {
    Pop-Location
}

[ordered]@{
    task = 'U0-02'
    sha = $sha
    adr_count = $adrNames.Count
    required_sections_per_adr = $headings.Count
    planned_acceptance_scenarios = $testIds.Count
    checked_markdown_files = $files.Count
    checked_local_file_links = $localLinks
    markdown_anchor_slugs_checked = $false
    business_diff_exit_code = $businessDiffExitCode
    changes_limited_to_readme_and_docs = ($errors.Count -eq 0)
    business_tests_run = $false
    errors = @($errors)
} | ConvertTo-Json -Depth 4

if ($errors.Count -gt 0) { exit 1 }
