# Chack

Chack is a Dockerized chatbot with autonomous capabilities. It currently supports Telegram (DMs and groups) and uses LangChain with a configurable model (default: `gpt-5.1-codex-max`).

## Features
- Telegram DMs and group chats with allowlists and regex triggers.
- Configurable tools: local command execution, DuckDuckGo search, Brave Search API.
- Optional cloud toolchains inside the container (AWS CLI, GCloud, Azure CLI, Stripe CLI, curl).
- YAML config with env interpolation for secrets.

## Quick start
1) Copy the example config and env file:

```bash
cp config/chack.yaml.example config/chack.yaml
cp .env.example .env
```

2) Fill in `.env` values (at least `OPENAI_API_KEY` and `TELEGRAM_BOT_TOKEN`).

3) Start the container:

```bash
docker compose up --build
```

## Configuration
Edit `config/chack.yaml` (env vars in `${VAR}` format are supported).

### Telegram filtering
Chack decides whether to respond based on:
- DMs: `allow_dms`, plus optional allowlists and `dm_require_regex`.
- Groups: `allow_groups`, plus optional allowlists and `group_require_regex`.

Examples:
- Allow only DMs from specific users: `dm_allowlist_ids` or `dm_allowlist_usernames`.
- Require group mentions like `^chack\b` with `group_require_regex`.

### Tools
Chack always receives these tools when enabled:
- `exec`: run local shell commands inside the container.
- `duckduckgo_search`: free web search.
- `brave_search`: Brave Search API (requires `BRAVE_API_KEY`).

### Model
Set the model in `model.primary` in `config/chack.yaml`.

## Files of interest
- `config/chack.yaml.example`
- `docker-compose.yml`
- `Dockerfile`
- `chack/` (Python source)

## Notes
- The container expects GCP credentials at `./gcp-credentials.json` if you use GCloud.
- The reply includes a short summary plus a list of tool actions used for the request.
