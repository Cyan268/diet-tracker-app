# Read-only documentation link and whitespace checks for U1-01.
param([string]$RepositoryRoot = (Join-Path $PSScriptRoot '../../..'))
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$files = @('README.md', 'deploy/README.md', 'docs/ARCHITECTURE.md', 'docs/ROADMAP.md',
    'docs/METRICS.md', 'docs/LEARNING_LOG.md', 'docs/INTERVIEW_QA.md',
    'docs/UPGRADE_DEVELOPMENT_PLAN.md', 'docs/upgrade/tasks/U1-01.md',
    'docs/upgrade/RISKS.md', 'docs/decisions/ADR-009-single-vps-and-worker.md')
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
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { $errors.Add("Broken: $file -> $target") }
    }
}
Push-Location $root
try {
    git -c core.safecrlf=false diff --check
    if ($LASTEXITCODE -ne 0) { $errors.Add('git diff --check failed') }
} finally { Pop-Location }
[ordered]@{ task='U1-01'; files=$files.Count; local_file_links=$links; anchor_slugs_checked=$false; errors=@($errors) } | ConvertTo-Json
if ($errors.Count -gt 0) { exit 1 }
