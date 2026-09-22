# One-shot server setup for voiceDeck deploy

This script prepares a fresh Ubuntu/Debian VPS for the `stashash/voiceDeck` GitHub Actions deploy.

## Usage (as root)

```bash
curl -fsSL https://raw.githubusercontent.com/stashash/voiceDeck/main/scripts/deploy/server-setup.sh \
  | sudo \
      IMAGE='ghcr.io/stashash/voicedeck:latest' \
      APP_PORT='8088' \
      DEPLOY_PUBKEY='<paste the RSA public key here>' \
      bash
```

## What it does

1. Installs Docker + compose plugin if missing.
2. Creates a passwordless `deploy` user with `docker` group.
3. Creates `/opt/voicedeck` (owned by `deploy`).
4. Writes `compose.yaml` (image + port from env) and `.env`.
5. Adds the GitHub Actions deploy public key to `~deploy/.ssh/authorized_keys` (idempotent).

## Where to get the deploy public key

On the machine that originally generated the key (`C:\Users\Admin\.ssh\voicedeck_deploy_key.pub`):

```powershell
Get-Content $env:USERPROFILE\.ssh\voicedeck_deploy_key.pub
```

That line goes into `DEPLOY_PUBKEY` above.

## After setup

1. Update repository secrets at https://github.com/stashash/voiceDeck/settings/secrets/actions:
   - `DEPLOY_HOST` = your VPS hostname or IP
   - `DEPLOY_PORT` = SSH port (default 22)
   - `DEPLOY_USER` = `deploy`
   - `DEPLOY_PATH` = `/opt/voicedeck`
   - `DEPLOY_SSH_KEY` = full contents of `C:\Users\Admin\.ssh\voicedeck_deploy_key`
2. Trigger workflow_dispatch:
   - https://github.com/stashash/voiceDeck/actions/workflows/deploy.yml → Run workflow
   - `image_tag` = `latest`, `dry_run` = `false`

## Test SSH from local machine

```bash
ssh -i ~/.ssh/voicedeck_deploy_key deploy@<vps-host>
```

If it logs in without password, GitHub Actions will too.
