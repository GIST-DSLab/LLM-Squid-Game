# CLI seats of squid5 run here when their config says `sandbox: docker` (squid5/core/providers.py). Nothing of the
# host is copied in: the engine mounts one empty per-call directory and passes the login by environment
# (CLAUDE_CODE_OAUTH_TOKEN for claude; a copied auth.json under CODEX_HOME for codex). Versions are pinned so the
# harness the models see does not change between runs; bump them on purpose and record it.
#   docker build -t squid5-agent-cli:latest -f docker/agent-cli.Dockerfile docker/
FROM node:22-slim
ARG CLAUDE_CODE_VERSION=2.1.288
ARG CODEX_VERSION=0.160.0
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} @openai/codex@${CODEX_VERSION} \
 && npm cache clean --force
USER node
ENV HOME=/home/node
WORKDIR /home/node
