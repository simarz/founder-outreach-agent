# Provisions Azure resources and deploys the Founder Follow-up Agent.
#
# Prerequisites (install once):
#   - Azure CLI:                winget install Microsoft.AzureCLI
#   - Azure Functions Core Tools: winget install Microsoft.Azure.FunctionsCoreTools
#   - Run `az login` first.
#
# Then from the azure-function folder:
#   powershell -ExecutionPolicy Bypass -File .\deploy.ps1
#
# Edit the variables below before first run if you like. Resource names that
# must be globally unique (storage, function app) get a random suffix.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# ---- configurable ----------------------------------------------------------
$Location       = "eastus"
$ResourceGroup  = "founder-followup-rg"
$Suffix         = -join ((48..57) + (97..122) | Get-Random -Count 6 | ForEach-Object {[char]$_})
$StorageAccount = "followupst$Suffix"          # 3-24 chars, lowercase/numbers
$FunctionApp    = "founder-followup-$Suffix"   # globally unique

# ---- secrets / settings ----------------------------------------------------
$NotifyEmail    = "your-email@example.com"
$LabelName      = "founders"
$FollowupDays   = "7"
$MaxFollowups   = "2"   # stop reminding after this many unanswered follow-ups
$SheetId        = ""    # Google Sheet ID to mirror the tracking table into (blank = off)
$TokenFile      = Join-Path (Split-Path $PSScriptRoot -Parent) "token.json"

if (-not (Test-Path $TokenFile)) {
    Write-Error "token.json not found at $TokenFile. Run the local main.py once to generate it (see ../README.md)."
}
$TokenJson = Get-Content $TokenFile -Raw

Write-Host "Creating resource group '$ResourceGroup'..." -ForegroundColor Cyan
az group create --name $ResourceGroup --location $Location | Out-Null

Write-Host "Creating storage account '$StorageAccount'..." -ForegroundColor Cyan
az storage account create --name $StorageAccount --resource-group $ResourceGroup `
    --location $Location --sku Standard_LRS | Out-Null

Write-Host "Creating Function App '$FunctionApp' (Python 3.11, consumption)..." -ForegroundColor Cyan
az functionapp create --name $FunctionApp --resource-group $ResourceGroup `
    --storage-account $StorageAccount --consumption-plan-location $Location `
    --runtime python --runtime-version 3.11 --functions-version 4 --os-type Linux | Out-Null

Write-Host "Applying application settings..." -ForegroundColor Cyan
az functionapp config appsettings set --name $FunctionApp --resource-group $ResourceGroup --settings `
    "NOTIFY_EMAIL=$NotifyEmail" `
    "LABEL_NAME=$LabelName" `
    "FOLLOWUP_DAYS=$FollowupDays" `
    "MAX_FOLLOWUPS=$MaxFollowups" `
    "SHEET_ID=$SheetId" `
    "STATE_CONTAINER=followup-state" `
    "WEBSITE_TIME_ZONE=Eastern Standard Time" `
    "AzureWebJobsFeatureFlags=EnableWorkerIndexing" | Out-Null

# Set the token JSON separately. Its value contains spaces and quotes, so batching
# it with the settings above can break the whole command (Azure CLI applies the
# batch atomically). Passing it as a single explicit argument avoids that.
az functionapp config appsettings set --name $FunctionApp --resource-group $ResourceGroup `
    --settings "GMAIL_TOKEN_JSON=$TokenJson" | Out-Null

Write-Host "Publishing function code..." -ForegroundColor Cyan
func azure functionapp publish $FunctionApp --python

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Function App: $FunctionApp"
Write-Host "Test now with:  func azure functionapp logstream $FunctionApp"
Write-Host "Manual run URL is shown above (run_now). The daily timer fires at 8 AM (WEBSITE_TIME_ZONE)."
