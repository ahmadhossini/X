# XAI V2 Oracle Cloud test installation

Use an OCI Ampere A1 Flex VM with Ubuntu 24.04 ARM64. Oracle currently documents 2 OCPUs and 12 GB RAM total as the Always Free A1 allocation for a free tenancy.

## 1. Prepare the VM

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip build-essential postgresql redis-server
sudo systemctl enable --now postgresql redis-server
```

## 2. Clone only the V2 branch

```bash
sudo mkdir -p /opt/xai-code-agent
sudo chown "$USER":"$USER" /opt/xai-code-agent
git clone --branch xai-v2-production-architecture --single-branch https://github.com/goodahmad001o-lang/X.git /opt/xai-code-agent
cd /opt/xai-code-agent
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## 3. Local services

Create a PostgreSQL database and user, then set:

```text
DATABASE_URL=postgresql+psycopg2://xai:<password>@127.0.0.1:5432/xai
REDIS_URL=redis://127.0.0.1:6379/0
```

Keep PostgreSQL and Redis bound to localhost and do not open their ports in the OCI security list.

## 4. Environment

Create `/etc/xai-code-agent.env` with the values required by `core/config.py`, including Telegram, Gemini, GitHub App, public URL, and TON settings.

Do not put this file in Git.

## 5. Run the three V2 components

Terminal 1:

```bash
cd /opt/xai-code-agent
set -a; source /etc/xai-code-agent.env; set +a
.venv/bin/python main.py
```

This process starts FastAPI and the Telegram polling bot together.

Terminal 2:

```bash
cd /opt/xai-code-agent
set -a; source /etc/xai-code-agent.env; set +a
.venv/bin/arq app.workers.arq_worker.WorkerSettings
```

PostgreSQL and Redis run as OS services.

## 6. First health check

```bash
curl http://127.0.0.1:10000/health
```

Expected response includes `status: ok` and `queue: redis`.

## 7. Public HTTPS

For GitHub App callbacks/webhooks and the Telegram Mini App, put an HTTPS reverse proxy in front of port 10000 and set `PUBLIC_BASE_URL` and `MINIAPP_URL` to the public HTTPS URL.

Only ports 22 and 80/443 should be exposed publicly for the test server. Do not expose PostgreSQL 5432 or Redis 6379.

## 8. Production-like process management

After the first manual smoke test passes, convert the two commands above into systemd services. Keep the API/bot process and ARQ worker as separate services so the worker can restart without taking the Telegram/API process down.
