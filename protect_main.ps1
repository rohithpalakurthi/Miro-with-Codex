$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$repo = "rohithpalakurthi/Miro-with-Codex"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Host "GitHub CLI is not installed here. Install gh or enable branch protection in GitHub UI." -ForegroundColor Yellow
  Write-Host "Recommended: Settings > Branches > Add rule > main > require pull request before merging."
  exit 1
}

Write-Host "Enabling branch protection for $repo main..." -ForegroundColor Cyan
gh api -X PUT "repos/$repo/branches/main/protection" `
  -H "Accept: application/vnd.github+json" `
  -f required_pull_request_reviews='{"required_approving_review_count":1}' `
  -f enforce_admins=true `
  -f restrictions=null `
  -f required_status_checks='{"strict":true,"contexts":[]}'

Write-Host "Branch protection request sent." -ForegroundColor Green
