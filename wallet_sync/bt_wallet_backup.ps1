# bt_wallet_backup.ps1
# ? Windows ???,?? scp ??????? ~/.bittensor/wallets
# ?????????????? backups\ ???

# ========== ?? ==========
$sshKey    = "$PSScriptRoot\peterqiao_private"   # ????????
$walletDir = ".bittensor/wallets"
$backupDir = Join-Path $PSScriptRoot "backups"
$dateTag   = Get-Date -Format "yyyyMMdd_HHmmss"

$hosts = @(
    "root@srv02.3518.pro",
    "root@ln1.3518.pro",
    "root@192.168.100.108"
)
# ==========================

# ?? backup ????
if (!(Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

foreach ($host in $hosts) {
    # ? host ????????
    $safeHost = ($host -replace "[@.:]", "_")
    $dest = Join-Path $backupDir "${safeHost}__${dateTag}"
    New-Item -ItemType Directory -Path $dest | Out-Null

    Write-Host ">>> ?? $host ? $dest"

    # ?? scp ??
    & scp.exe -i $sshKey -r "$host:~/$walletDir/*" "$dest/"
}

Write-Host "=== ????,????? $backupDir ==="
