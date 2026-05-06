# Vaultwarden Backup and Restore Scripts

This directory mirrors the scripts deployed on the two N1 hosts.

## 192.168.1.11

Vaultwarden source host. This host owns the live Vaultwarden Docker data volume.

- `deploy.sh`: validates local backup prerequisites and deploys scripts.
- `backup-local.sh`: runs `bruceforce/vaultwarden-backup:latest` against the `vaultwarden` container and writes local backup archives.
- `backup-now.sh`: same as `backup-local.sh`.
- `status.sh`: shows Vaultwarden mount, backup image, local backups, and recent logs.

Remote deployment path:

```bash
/root/workspace/vaultwarden-backup
```

## 192.168.100.11

Backup destination and scheduler host. This host pulls backups from `192.168.1.11` over VPN.

- `deploy.sh`: validates pull-side prerequisites and installs the daily cron job.
- `pull-backup.sh`: triggers `192.168.1.11` backup and pulls archives into `backups/`.
- `status.sh`: shows cron, destination backups, and recent logs.

Remote deployment path:

```bash
/root/workspace/vaultwarden-backup
```

Daily cron:

```cron
0 5 * * * root /root/workspace/vaultwarden-backup/pull-backup.sh >> /root/workspace/vaultwarden-backup/logs/backup.log 2>&1
```

## 192.168.100.11/restore-test

Standalone restore test environment on `192.168.100.11`.

- `restore-latest.sh`: stops the restore containers, restores the latest backup, starts Vaultwarden and HTTPS proxy, then health-checks them.
- `start.sh`: starts the HTTP Vaultwarden restore container through Docker Compose.
- `stop.sh`: stops the Vaultwarden restore container.
- `status.sh`: shows restore container status, `/alive`, and restored data files.
- `docker-compose.yml`: Vaultwarden restore container definition.
- `nginx.conf`: HTTPS proxy config for browser extension testing.

Remote deployment path:

```bash
/root/workspace/vaultwarden-backup/restore-test
```

Restore test URL:

```text
https://192.168.100.11:18443
```
