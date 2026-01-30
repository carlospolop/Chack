# Chack

Chack is a Dockerized chatbot with autonomous capabilities. It supports Telegram (DMs + groups) and Discord, and uses LangChain with configurable models.

## Features
- Telegram and Discord support with allowlists and regex triggers.
- Tooling: local command execution, DuckDuckGo search, Brave Search API.
- Cloud toolchains inside the container (AWS CLI, GCloud, Azure CLI, Stripe CLI, GitHub CLI, Terraform).
- YAML config with env interpolation and tool prompt injection.
- Short-term memory + optional long-term memory per chat/thread.
- Cost/usage tracking per request (rounds/tools/estimated cost suffix).

## Quick start
1) Copy the example config:

```bash
cp config/chack.yaml.example config/chack.yaml
```

2) Fill in `config/chack.yaml` (at least `openai_api_key` and `telegram.token` or `discord.token`).

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

### Discord filtering
Chack decides whether to respond based on:
- `channel_ids`: only these channels (threads are allowed if their parent channel is listed).
- `trigger_words`: message must contain one of these words (case-insensitive).

### Tools
Chack always receives these tools when enabled:
- `exec`: run local shell commands inside the container.
- `duckduckgo_search`: free web search.
- `brave_search`: Brave Search API (requires `brave_api_key`).

### Tools prompt
If `system_prompt` (or `discord.system_prompt`) contains `$$TOOLS$$`, it is replaced at startup
with the contents of `config/TOOLS.md`.

### Model
- `model.primary`: main agent model (tool-calling + task execution).
- `model.chat`: chat-oriented model (used in memory summarization and chat-only calls).

## Files of interest
- `config/chack.yaml.example`
- `config/TOOLS.md`
- `DISCORD_SETUP.md`
- `docker-compose.yml`
- `Dockerfile`
- `chack/` (Python source)

## Notes
- Credentials live in `config/chack.yaml` under `credentials` and are exported into the container at startup.
- Long-term memory is stored per chat/thread in the configured `long_term_memory_dir`.
- Discord messages are answered inside a thread; a short “Working on it…” status is posted and removed.
