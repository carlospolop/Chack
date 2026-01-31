import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _interpolate_env(value: Any) -> Any:
    if isinstance(value, str):
        def _replace(match: re.Match) -> str:
            var = match.group(1)
            return os.environ.get(var, "")

        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    return value


@dataclass
class ModelConfig:
    primary: str
    temperature: float = 0.2
    chat: str = ""


@dataclass
class AgentConfig:
    backend: str = "langchain"


@dataclass
class TelegramConfig:
    enabled: bool = True
    token: str = ""
    allow_dms: bool = True
    dm_allowlist_ids: List[int] = field(default_factory=list)
    dm_allowlist_usernames: List[str] = field(default_factory=list)
    dm_allowlist_usernames_regex: List[str] = field(default_factory=list)
    dm_require_regex: List[str] = field(default_factory=list)
    allow_groups: bool = True
    group_allowlist_ids: List[int] = field(default_factory=list)
    group_allowlist_title_regex: List[str] = field(default_factory=list)
    group_require_regex: List[str] = field(default_factory=list)
    max_turns: int = 75
    memory_max_messages: int = 16
    memory_reset_to_messages: int = 0
    memory_summary_prompt: str = ""
    memory_reset_minutes: int = 30
    long_term_memory_enabled: bool = True
    long_term_memory_max_chars: int = 1500
    long_term_memory_dir: str = "longterm"
    long_term_memory_summary_prompt: str = ""


@dataclass
class DiscordConfig:
    enabled: bool = False
    token: str = ""
    channel_ids: List[int] = field(default_factory=list)
    trigger_words: List[str] = field(default_factory=list)
    max_turns: int = 50
    memory_max_messages: int = 16
    memory_reset_to_messages: int = 0
    memory_summary_prompt: str = ""
    memory_reset_minutes: int = 30
    long_term_memory_enabled: bool = True
    long_term_memory_max_chars: int = 1500
    long_term_memory_dir: str = "longterm"
    long_term_memory_summary_prompt: str = ""
    system_prompt: str = ""  # If empty, uses main system_prompt


@dataclass
class ToolsConfig:
    exec_enabled: bool = True
    exec_timeout_seconds: int = 120
    exec_max_output_chars: int = 5000
    duckduckgo_enabled: bool = True
    duckduckgo_max_results: int = 6
    brave_enabled: bool = True
    brave_api_key: str = ""
    brave_max_results: int = 6
    min_tools_used: int = 10


@dataclass
class CredentialsConfig:
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = ""
    aws_profiles: Dict[str, Dict[str, str]] = field(default_factory=dict)
    stripe_api_key: str = ""
    gcp_credentials_path: str = ""
    gcp_quota_project: str = ""
    azure_app_id: str = ""
    azure_sa_name: str = ""
    azure_sa_secret_value: str = ""
    azure_tenant_id: str = ""
    gh_token: str = ""
    openai_api_key: str = ""
    openai_admin_key: str = ""
    openai_org_id: str = ""
    openai_org_ids: List[str] = field(default_factory=list)
    aws_profile: str = ""
    aws_credentials_file: str = ""


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class ChackConfig:
    model: ModelConfig
    agent: AgentConfig
    telegram: TelegramConfig
    discord: DiscordConfig
    tools: ToolsConfig
    credentials: CredentialsConfig
    logging: LoggingConfig
    system_prompt: str
    env: Dict[str, str]


def _load_section(data: Dict[str, Any], key: str, cls):
    section = data.get(key, {})
    if section is None:
        return cls()
    return cls(**section)


def load_config(path: str) -> ChackConfig:
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    raw = _interpolate_env(raw)

    tools_text: Optional[str] = None

    def _get_tools_text() -> str:
        nonlocal tools_text
        if tools_text is not None:
            return tools_text
        tools_path = os.path.join(os.path.dirname(path), "TOOLS.md")
        if not os.path.exists(tools_path):
            raise ValueError("TOOLS.md is required when using $$TOOLS$$ in system_prompt")
        with open(tools_path, "r", encoding="utf-8") as handle:
            tools_text = handle.read().strip()
        return tools_text

    if "system_prompt" not in raw or not str(raw.get("system_prompt", "")).strip():
        raise ValueError("system_prompt is required in config/chack.yaml")
    if "model" not in raw or not isinstance(raw.get("model"), dict):
        raise ValueError("model.primary is required in config/chack.yaml")
    if not str(raw.get("model", {}).get("primary", "")).strip():
        raise ValueError("model.primary is required in config/chack.yaml")

    system_prompt = str(raw.get("system_prompt")).strip()
    if "$$TOOLS$$" in system_prompt:
        system_prompt = system_prompt.replace("$$TOOLS$$", _get_tools_text())

    credentials = _load_section(raw, "credentials", CredentialsConfig)
    if isinstance(credentials.aws_profiles, str) and credentials.aws_profiles.strip():
        try:
            parsed_profiles = yaml.safe_load(credentials.aws_profiles) or {}
            if isinstance(parsed_profiles, dict):
                credentials.aws_profiles = parsed_profiles
        except yaml.YAMLError:
            credentials.aws_profiles = {}
    if isinstance(credentials.openai_org_ids, str):
        credentials.openai_org_ids = [
            item.strip() for item in credentials.openai_org_ids.split(",") if item.strip()
        ]

    telegram = _load_section(raw, "telegram", TelegramConfig)
    # Coerce ID lists to ints when provided as strings.
    telegram.dm_allowlist_ids = [
        int(x) for x in telegram.dm_allowlist_ids if str(x).strip()
    ]
    telegram.group_allowlist_ids = [
        int(x) for x in telegram.group_allowlist_ids if str(x).strip()
    ]
    if telegram.allow_dms:
        if not (
            telegram.dm_allowlist_ids
            or telegram.dm_allowlist_usernames
            or telegram.dm_allowlist_usernames_regex
        ):
            raise ValueError(
                "telegram.allow_dms is true, but no DM allowlist is configured. "
                "Set dm_allowlist_ids, dm_allowlist_usernames, or dm_allowlist_usernames_regex."
            )
    if telegram.allow_groups:
        if not (telegram.group_allowlist_ids or telegram.group_allowlist_title_regex):
            raise ValueError(
                "telegram.allow_groups is true, but no group allowlist is configured. "
                "Set group_allowlist_ids or group_allowlist_title_regex."
            )

    discord = _load_section(raw, "discord", DiscordConfig)
    if discord.system_prompt and "$$TOOLS$$" in discord.system_prompt:
        discord.system_prompt = discord.system_prompt.replace("$$TOOLS$$", _get_tools_text())
    # Coerce channel IDs to ints
    discord.channel_ids = [
        int(x) for x in discord.channel_ids if str(x).strip()
    ]

    config = ChackConfig(
        model=_load_section(raw, "model", ModelConfig),
        agent=_load_section(raw, "agent", AgentConfig),
        telegram=telegram,
        discord=discord,
        tools=_load_section(raw, "tools", ToolsConfig),
        credentials=credentials,
        logging=_load_section(raw, "logging", LoggingConfig),
        system_prompt=system_prompt,
        env=raw.get("env", {}) or {},
    )

    return config
