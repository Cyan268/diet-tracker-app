# Read-only link and working-tree whitespace verification for U4-01.
param([string]$RepositoryRoot = (Join-Path $PSScriptRoot '../../..'))
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$files = @(
    'README.md', 'docs/ARCHITECTURE.md', 'docs/ROADMAP.md', 'docs/METRICS.md',
    'docs/LEARNING_LOG.md', 'docs/INTERVIEW_QA.md', 'docs/UPGRADE_DEVELOPMENT_PLAN.md',
    'docs/upgrade/tasks/U4-01.md', 'docs/upgrade/RISKS.md',
    'docs/decisions/ADR-007-cursor-sync-and-conflict-resolution.md',
    'docs/decisions/ADR-014-ordered-sync-and-snapshots.md'
)
$errors = [System.Collections.Generic.List[string]]::new()
$links = 0
foreach ($file in $files) {
    $path = Join-Path $root $file
    $content = Get-Content -LiteralPath $path -Raw -Encoding utf8
    foreach ($match in [regex]::Matches($content, '(?<!!)\[[^\]\r\n]+\]\(([^)\r\n]+)\)')) {
        $target = $match.Groups[1].Value.Trim('<', '>')
        if ($target -match '^(https?://|mailto:|#)') { continue }
        $target = [uri]::UnescapeDataString(($target -split '#', 2)[0])
        $resolved = [IO.Path]::GetFullPath((Join-Path (Split-Path $path -Parent) $target))
        $links++
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            $errors.Add("Broken link: $file -> $target")
        }
    }
}
Push-Location $root
try {
    git -c core.safecrlf=false diff --check
    $diffExit = $LASTEXITCODE
    if ($diffExit -ne 0) { $errors.Add('git diff --check failed') }
} finally { Pop-Location }
[ordered]@{
    task = 'U4-01'
    checked_markdown_files = $files.Count
    local_file_links = $links
    anchor_slugs_checked = $false
    diff_check_exit = $diffExit
    errors = @($errors)
} | ConvertTo-Json -Depth 3
if ($errors.Count -gt 0) { exit 1 }
