# Oracle Cloud test deployment

This directory prepares an Ubuntu ARM64 Oracle Cloud VM for the V2 architecture.

Target branch: `xai-v2-production-architecture`

Services on one VM:
- FastAPI + Telegram Bot: `xai-code-agent.service`
- ARQ Worker: `xai-code-agent-worker.service`
- PostgreSQL: local
- Redis: local

The deployment files are intentionally separate from application code and do not contain project secrets.

Before GitHub webhook or Mini App callback testing, configure a real HTTPS public URL and set `PUBLIC_BASE_URL` and `MINIAPP_URL` in the server environment.

Do not expose PostgreSQL or Redis publicly.
