# Sets up failure alerting for the Founder Follow-up Agent.
#
# What it does:
#   1. Creates a Log Analytics workspace + Application Insights (if missing) and
#      connects the Function App to it, so function failures are recorded.
#   2. Creates an action group that emails you.
#   3. Creates a log-query alert that fires whenever a function run fails
#      (e.g. the Gmail token expired, or any unhandled error).
#
# Run from this folder, after `az login`:
#   powershell -ExecutionPolicy Bypass -File .\setup_alerts.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# ---- configurable ----------------------------------------------------------
$RG          = "founder-followup-rg"
$Location    = "eastus"
$FunctionApp = "founder-followup-kp8sei"   # <-- your keeper app
$AlertEmail  = "your-email@example.com"

$Workspace   = "founder-followup-logs"
$AppInsights = "founder-followup-ai"
$ActionGroup = "founder-followup-alerts"
$AgShort     = "fupalert"                  # max 12 chars
$AlertName   = "founder-followup-failures"
# ---------------------------------------------------------------------------

Write-Host "Ensuring required CLI extensions are installed (no prompts)..." -ForegroundColor Cyan
# Allow CLI extensions to install without an interactive Y/n prompt (which would
# otherwise hang this non-interactive script at the scheduled-query step).
az config set extension.use_dynamic_install=yes_without_prompt --only-show-errors 2>$null
az extension add --name application-insights --only-show-errors 2>$null
az extension add --name scheduled-query --only-show-errors 2>$null

Write-Host "Creating Log Analytics workspace '$Workspace'..." -ForegroundColor Cyan
az monitor log-analytics workspace create -g $RG -n $Workspace -l $Location --only-show-errors | Out-Null
$WsId = az monitor log-analytics workspace show -g $RG -n $Workspace --query id -o tsv

Write-Host "Creating Application Insights '$AppInsights'..." -ForegroundColor Cyan
az monitor app-insights component create --app $AppInsights -g $RG -l $Location `
    --workspace $WsId --application-type web --only-show-errors | Out-Null
$AiId   = az monitor app-insights component show --app $AppInsights -g $RG --query id -o tsv
$AiConn = az monitor app-insights component show --app $AppInsights -g $RG --query connectionString -o tsv

Write-Host "Connecting the Function App to Application Insights..." -ForegroundColor Cyan
az functionapp config appsettings set -n $FunctionApp -g $RG `
    --settings "APPLICATIONINSIGHTS_CONNECTION_STRING=$AiConn" --only-show-errors | Out-Null

Write-Host "Creating action group (emails $AlertEmail)..." -ForegroundColor Cyan
az monitor action-group create -n $ActionGroup -g $RG --short-name $AgShort `
    --action email admin $AlertEmail --only-show-errors | Out-Null
$AgId = az monitor action-group show -n $ActionGroup -g $RG --query id -o tsv

Write-Host "Creating failure alert rule '$AlertName'..." -ForegroundColor Cyan
az monitor scheduled-query create -n $AlertName -g $RG `
    --scopes $AiId `
    --condition "count 'failed' > 0" `
    --condition-query failed="requests | where success == false" `
    --evaluation-frequency 6h --window-size 6h --severity 1 `
    --action-groups $AgId `
    --description "Founder follow-up agent: a scheduled run failed. Check the Gmail token (it may have expired) and the function logs." `
    --only-show-errors | Out-Null

Write-Host ""
Write-Host "Alerting is set up." -ForegroundColor Green
Write-Host "You'll get an email at $AlertEmail within ~6 hours of any failed run."
Write-Host "Test it anytime from the Portal: Monitor -> Alerts -> $AlertName -> ... (or just let a real failure trigger it)."
