# Azure deployment (v2)

This app is four processes: **Postgres**, **API** (`uvicorn`), **worker** (polls jobs and runs OCR + Groq), and **frontend** (nginx, proxies `/api` to the API). They already run together via `docker-compose.yml`.

## 1. VM vs App Service vs “pay only when used”

**Use a small Azure Linux VM and `docker compose`.** Do not use Azure App Service for this app.

| Option | What billing actually does | Fit for this app |
| --- | --- | --- |
| **Azure VM** (recommended) | You pay while the VM is **running**. Deallocate it in the portal and compute drops to ~$0 (you still pay a little for the disk). | Best match. Compose, local receipt files, PaddleOCR models on disk, and the always-polling worker all work with no code changes. |
| **Azure App Service** | A paid App Service **plan bills 24/7**, even with zero users. Free F1 sleeps after idle, but it cannot run this Docker stack (OCR image, worker, Postgres, 4 containers). | Poor fit. You pay like a VM without getting Compose, a background worker, or persistent local files for free. |
| **Azure Container Apps** | This is the real scale-to-zero product: replicas can go to 0 and you pay per vCPU-second while running. | Possible later, not first. Needs Azure Container Registry, Azure Database for PostgreSQL, Blob storage (code change), and the **worker must not scale to 0** or jobs never process. OCR images are large, so cold starts are slow. |

Why App Service “sleeps when unused” is the wrong mental model here:

- Paid App Service does **not** stop billing when idle.
- This worker is a forever loop (`python -m app.worker`). If compute sleeps, queued receipts sit forever.
- PaddleOCR + torch is a heavy image. First request after sleep can take minutes (or fail) while models load.
- Receipts are stored on the local filesystem (`backend/data/objects`). App Service disks are ephemeral unless you add Azure Files/Blob.

**Cost control on the recommended path:** leave the VM on while you use the app; **Stop / deallocate** it when you are done. Same idea you wanted from App Service, without fighting the architecture.

Suggested VM size:

- **Minimum to try:** `Standard_B2s` (2 vCPU, 4 GB) — may OOM during OCR.
- **Recommended:** `Standard_B2ms` (2 vCPU, 8 GB) in a region close to you (for example `centralindia`).

You will also pay a little for the OS disk (and public IP if Standard SKU). Postgres on the same VM is fine for a personal/demo deploy. Move it to Azure Database for PostgreSQL only if you need backups, HA, or to stop treating the VM as the database.

## 2. What you need to provide

Fill this in before anyone (or any script) can deploy. **Never commit real values.** See [section 3](#3-secrets-do-not-put-env-in-git) for how to store them and copy them onto the VM.

### Azure account

| Item | Example | Notes |
| --- | --- | --- |
| Azure subscription | Pay-As-You-Go / student | `az account show` |
| Region | `centralindia` | Same region for VM + public IP |
| Resource group name | `rg-expense-v2` | New empty group is fine |
| VM name | `vm-expense-v2` | DNS label must be unique in the region |
| VM size | `Standard_B2ms` | See above |
| Admin username | `azureuser` | Linux user on the VM |
| SSH public key | `~/.ssh/id_ed25519.pub` | Password login is a bad idea |

### App secrets and config

| Variable | Required | What to set in production |
| --- | --- | --- |
| `EXPENSE_V2_GROQ_API_KEY` | Yes | Your Groq key. OCR/agent calls fail without it. |
| `EXPENSE_V2_GROQ_BASE_URL` | No | Default `https://api.groq.com/openai/v1` |
| `EXPENSE_V2_MODEL` | No | Default `qwen/qwen3.8-27b` |
| `EXPENSE_V2_JWT_SECRET` | Yes | Long random string, not the example value |
| `EXPENSE_V2_POSTGRES_PASSWORD` | Yes | Strong password, not `expense` |
| `EXPENSE_V2_BOOTSTRAP_EMAIL` | Yes | First owner login |
| `EXPENSE_V2_BOOTSTRAP_PASSWORD` | Yes | Strong password, not `change-me-now` |
| `EXPENSE_V2_BOOTSTRAP_ORGANIZATION` | No | Display name for the first org |
| `EXPENSE_V2_CORS_ORIGINS` | Yes | Public origin, e.g. `http://<VM_PUBLIC_IP>` or `https://your.domain` |
| `VITE_API_BASE_URL` | Keep empty | Empty means the browser uses same-origin `/api` (nginx proxy). Correct for this Compose setup. |

Optional later:

| Item | When |
| --- | --- |
| Custom domain | You want `https://expenses.example.com` instead of a raw IP |
| TLS certificate | Always, once you have a domain (Let’s Encrypt) |
| GitHub repo access on the VM | Deploy by `git clone` (this repo is public, or use a deploy key) |

Local ports (`3000`, `8000`, `5432`) stay as Compose defaults **inside** the VM. Only **22** (SSH) and **80** (and **443** if you add TLS) should be open on the Azure NSG. Do not expose Postgres or the API port to the internet.

## 3. Secrets: do not put `.env` in git

Git holds the **template**, not the secrets. Compose on the VM reads a real `.env` file that never leaves your machine / Azure.

| File | In git? | Purpose |
| --- | --- | --- |
| `.env.example` | Yes | Safe placeholders. Clone + copy this. |
| `.env` | **No** (gitignored) | Real passwords, JWT secret, Groq key. Local laptop **and** VM only. |

How the running app gets values today: `docker-compose.yml` has `env_file: .env` on `postgres`, `api`, `worker`, and `frontend`. Docker injects those variables into the containers at start. There is no need to bake secrets into the image or the GitHub repo.

```text
Laptop (gitignored .env)
        │  scp  or  Key Vault → write file
        ▼
VM:  /home/azureuser/agentic-ai/v2/.env   (chmod 600)
        │  docker compose env_file
        ▼
Containers: API, worker, Postgres, frontend
```

Keep **three copies** of the real secrets, none of them in git:

1. **Laptop** — `v2/.env` next to the code you already run locally (already gitignored).
2. **VM disk** — same file on the server so Compose can read it. The OS disk survives deallocate, so this file is still there when you start the VM again.
3. **Offline backup** — password manager (1Password / Bitwarden) **or** Azure Key Vault. Needed if you recreate the VM.

Never commit `.env`, paste it into chat/PRs, or store it in another git repo. Confirm it is ignored:

```bash
cd v2
git check-ignore -v .env    # should print .gitignore
git status                  # .env must not appear
```

If `.env` ever lands in git history, treat every secret as leaked: rotate Groq key, JWT secret, DB password, and bootstrap password, then remove the file from git.

### 3.1 Recommended for this VM deploy: copy `.env` over SSH

On the **laptop**, keep two gitignored files (`.env.*` is ignored except `.env.example`):

- `v2/.env` — local Docker (`localhost` CORS, local DB password).
- `v2/.env.production` — VM values (public IP CORS, strong secrets). Copy from `.env.example` and fill production values.

After the repo exists on the VM:

```bash
# from your laptop, in agentic-ai/v2
# Compose on the VM always reads a file named .env
scp .env.production azureuser@<VM_PUBLIC_IP>:~/agentic-ai/v2/.env
```

Then on the **VM**:

```bash
chmod 600 ~/agentic-ai/v2/.env
# optional: block other users from reading the directory
chmod 700 ~/agentic-ai/v2
```

`git pull` will not overwrite `.env` because it is untracked. After you change `.env`, recreate containers so they pick up new values:

```bash
cd ~/agentic-ai/v2
docker compose up -d
```

Do not `docker compose build` just to change secrets. `env_file` is applied at container **create**, not baked into the image.

### 3.2 Better source of truth: Azure Key Vault

Use this if you do not want the only backup to be a file on your laptop. The VM still needs a `.env` on disk for Compose; Key Vault is where you **store** the values and **render** that file.

Create a vault once (laptop):

```bash
az keyvault create \
  --name kv-expense-v2 \
  --resource-group rg-expense-v2 \
  --location centralindia

az keyvault secret set --vault-name kv-expense-v2 --name groq-api-key --value '<your-groq-key>'
az keyvault secret set --vault-name kv-expense-v2 --name jwt-secret --value '<long-random-secret>'
az keyvault secret set --vault-name kv-expense-v2 --name postgres-password --value '<strong-db-password>'
az keyvault secret set --vault-name kv-expense-v2 --name bootstrap-email --value '<your-email>'
az keyvault secret set --vault-name kv-expense-v2 --name bootstrap-password --value '<strong-login-password>'
```

Give the VM a **managed identity** and Key Vault get permission so you are not copying `az login` credentials onto the box:

```bash
az vm identity assign --resource-group rg-expense-v2 --name vm-expense-v2
PRINCIPAL_ID=$(az vm identity show --resource-group rg-expense-v2 --name vm-expense-v2 --query principalId -o tsv)
az keyvault set-policy \
  --name kv-expense-v2 \
  --object-id "$PRINCIPAL_ID" \
  --secret-permissions get list
```

On the **VM**, render `.env` from Key Vault (requires Azure CLI on the VM):

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
az login --identity

VAULT=kv-expense-v2
cd ~/agentic-ai/v2
cp .env.example .env
chmod 600 .env

python3 <<'PY'
from pathlib import Path
import subprocess

def secret(name: str) -> str:
    return subprocess.check_output(
        ["az", "keyvault", "secret", "show", "--vault-name", "kv-expense-v2", "--name", name, "--query", "value", "-o", "tsv"],
        text=True,
    ).strip()

ip = subprocess.check_output(["curl", "-s", "ifconfig.me"], text=True).strip()
replacements = {
    "EXPENSE_V2_GROQ_API_KEY=": "EXPENSE_V2_GROQ_API_KEY=" + secret("groq-api-key"),
    "EXPENSE_V2_JWT_SECRET=": "EXPENSE_V2_JWT_SECRET=" + secret("jwt-secret"),
    "EXPENSE_V2_POSTGRES_PASSWORD=": "EXPENSE_V2_POSTGRES_PASSWORD=" + secret("postgres-password"),
    "EXPENSE_V2_BOOTSTRAP_EMAIL=": "EXPENSE_V2_BOOTSTRAP_EMAIL=" + secret("bootstrap-email"),
    "EXPENSE_V2_BOOTSTRAP_PASSWORD=": "EXPENSE_V2_BOOTSTRAP_PASSWORD=" + secret("bootstrap-password"),
    "EXPENSE_V2_CORS_ORIGINS=": f"EXPENSE_V2_CORS_ORIGINS=http://{ip}",
}
lines = []
for line in Path(".env").read_text().splitlines():
    replaced = False
    for prefix, new in replacements.items():
        if line.startswith(prefix):
            lines.append(new)
            replaced = True
            break
    if not replaced:
        lines.append(line)
Path(".env").write_text("\n".join(lines) + "\n")
print("wrote .env from Key Vault")
PY
```

Key Vault names must be globally unique; if `kv-expense-v2` is taken, pick another (`kv-expense-v2-<yourname>`).

### 3.3 What not to do

- Do not check in `.env` “just for deploy.”
- Do not put secrets in GitHub Actions logs, `docker-compose.override.yml` in git, or image `ENV`/`ARG` for keys.
- Do not email yourself the file. Use Key Vault or a password manager.
- Do not chmod `644` on `.env` on a shared VM.

When you move to Container Apps later, skip the file on disk: store the same values in Key Vault and map them as Container App secrets / env vars. Compose + VM still wants a file.

## 4. Step-by-step: deploy on an Azure VM

Run Azure CLI commands on your laptop. Commands on the VM are marked **(VM)**.

### 4.1 Laptop prerequisites

```bash
brew install azure-cli   # or https://learn.microsoft.com/cli/azure/install-azure-cli
az login
az account show
```

Confirm the subscription is the one you want to pay with.

### 4.2 Create resource group, VM, and HTTP access

Adjust names/region if you used different values in section 2.

```bash
az group create --name rg-expense-v2 --location centralindia

az vm create \
  --resource-group rg-expense-v2 \
  --name vm-expense-v2 \
  --image Ubuntu2204 \
  --size Standard_B2ms \
  --admin-username azureuser \
  --authentication-type ssh \
  --generate-ssh-keys \
  --public-ip-sku Standard

az vm open-port --resource-group rg-expense-v2 --name vm-expense-v2 --port 80 --priority 1001
```

`--generate-ssh-keys` writes `~/.ssh/id_rsa` if you do not already have one. To use an existing key:

```bash
--ssh-key-values ~/.ssh/id_ed25519.pub
```

Copy the VM public IP from the create output (`publicIpAddress`).

```bash
ssh azureuser@<VM_PUBLIC_IP>
```

### 4.3 (VM) Install Docker

```bash
sudo apt-get update
sudo apt-get install --yes ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install --yes docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
newgrp docker
docker compose version
```

### 4.4 (VM) Get the code

If the GitHub repo is public:

```bash
git clone --branch v2 https://github.com/varun00391/agentic-ai.git
cd agentic-ai/v2
```

Private repo: add a deploy key or `gh auth login`, then clone the `v2` branch the same way.

### 4.5 Put production `.env` on the VM

Do **not** create this file in git. From your **laptop**, after the clone in 4.4:

```bash
# in agentic-ai/v2 on the laptop (gitignored)
scp .env.production azureuser@<VM_PUBLIC_IP>:~/agentic-ai/v2/.env
```

If you do not have a production `.env` yet, copy `.env.example` on the laptop, fill the values from [section 2](#2-what-you-need-to-provide), then `scp`. Or render from Key Vault ([section 3.2](#32-better-source-of-truth-azure-key-vault)).

On the **VM**:

```bash
chmod 600 ~/agentic-ai/v2/.env
```

Required production values (same names as local):

```bash
VITE_API_BASE_URL=

EXPENSE_V2_POSTGRES_USER=expense
EXPENSE_V2_POSTGRES_PASSWORD=<strong-db-password>
EXPENSE_V2_POSTGRES_DB=expense_v2

EXPENSE_V2_JWT_SECRET=<long-random-secret>
EXPENSE_V2_CORS_ORIGINS=http://<VM_PUBLIC_IP>

EXPENSE_V2_GROQ_API_KEY=<your-groq-key>
EXPENSE_V2_GROQ_BASE_URL=https://api.groq.com/openai/v1
EXPENSE_V2_MODEL=qwen/qwen3.8-27b

EXPENSE_V2_BOOTSTRAP_EMAIL=<your-email>
EXPENSE_V2_BOOTSTRAP_PASSWORD=<strong-login-password>
EXPENSE_V2_BOOTSTRAP_ORGANIZATION=Local Org
```

`docker-compose.yml` already points the API/worker at Postgres on the Compose network and stores files under `/app/data/objects`. You do not need to change `EXPENSE_V2_DATABASE_URL` for Compose; the compose `environment:` block overrides it.

Generate a JWT secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4.6 (VM) Build and start

First build is slow (CPU torch + PaddleOCR). Give it 10–20 minutes and enough disk (~20 GB free).

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f api worker frontend
```

Healthy when:

- `postgres` is healthy
- `api` healthcheck passes
- `frontend` is up on port 80
- `worker` stays running (no healthcheck; it should not exit)

Open:

- App: `http://<VM_PUBLIC_IP>`
- Health: `http://<VM_PUBLIC_IP>/health`

Log in with `EXPENSE_V2_BOOTSTRAP_EMAIL` / `EXPENSE_V2_BOOTSTRAP_PASSWORD`. Upload a receipt and confirm the worker completes the job (`docker compose logs worker`).

### 4.7 Restart after reboot

Compose uses `restart: unless-stopped`, so containers come back after a VM reboot. Docker itself must be enabled (default after the install above).

```bash
sudo systemctl enable docker
```

### 4.8 Save money: stop the VM when idle

From your laptop:

```bash
az vm deallocate --resource-group rg-expense-v2 --name vm-expense-v2
az vm start --resource-group rg-expense-v2 --name vm-expense-v2
```

Deallocate = no VM compute charge. The public IP can change unless you use a **static** Standard public IP.

```bash
az network public-ip update \
  --resource-group rg-expense-v2 \
  --name vm-expense-v2PublicIP \
  --allocation-method Static
```

The public IP resource name may differ; list with `az network public-ip list -g rg-expense-v2 -o table`.

If the IP changes, update `EXPENSE_V2_CORS_ORIGINS` and recreate the API container (`docker compose up -d api`).

### 4.9 Optional: HTTPS + custom domain

1. Point an A record at the static public IP.
2. On the VM, install Caddy or certbot in front of the frontend (host port 80/443 → container 80), **or** add a Caddy service to Compose.
3. Set `EXPENSE_V2_CORS_ORIGINS=https://your.domain`.
4. Open NSG port 443.

Until then, the app is HTTP-only. Do not use a real password over the public internet without TLS.

### 4.10 Updates

```bash
cd ~/agentic-ai
git pull origin v2
cd v2
# .env is gitignored — pull does not replace it
docker compose up --build -d
```

Postgres data lives in the `postgres-data` Docker volume. Receipt images live in `./backend/data` on the VM. Do not delete those unless you intend to wipe data. `.env` lives on the VM OS disk and survives deallocate; back it up in Key Vault or a password manager before you **delete** the VM.

## 5. If you later want scale-to-zero (Container Apps)

Only do this after the VM path works. You will need:

- Azure Container Registry (build/push `backend` and `frontend` images)
- Azure Container Apps Environment
- Three apps: `frontend`, `api`, `worker` (worker **min replicas = 1**)
- Azure Database for PostgreSQL Flexible Server (can be stopped separately)
- Azure Blob Storage **and a code change** — today `ObjectStorage` writes local files, so API and worker must share a volume or you rewrite storage to Blob
- Frontend `nginx.conf` today proxies to hostname `api`; in Container Apps that becomes the internal FQDN of the API app
- Same secrets as section 3, stored in Key Vault and mapped as Container App env vars (no `.env` file on disk)

Frontend/API can use min replicas `0`. The worker cannot, unless you redesign jobs onto a queue (Service Bus / Storage Queue) and run worker as a Container Apps Job.

## 6. Checklist

On your laptop:

- [ ] Azure login works on the intended subscription
- [ ] Resource group + VM created
- [ ] NSG allows 22 (you) and 80 (users); 5432 and 8000 stay closed
- [ ] SSH into the VM works

On the VM:

- [ ] Docker Engine + Compose plugin installed
- [ ] `v2` branch cloned
- [ ] Production `.env` copied with `scp` or rendered from Key Vault (not committed)
- [ ] `chmod 600` on the VM `.env`
- [ ] `docker compose up --build -d` healthy
- [ ] Browser login + receipt upload + job completion works

Operations:

- [ ] Static public IP (if you will deallocate often)
- [ ] Domain + TLS (before sharing with others)
- [ ] Deallocate VM when nobody is using it
- [ ] `.env` is **not** in git (`git check-ignore -v .env`)
- [ ] Secrets backed up in a password manager or Key Vault (so a new VM can be rebuilt)
)
