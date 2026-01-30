import os
from typing import Optional


def _resolve_path(base_dir: str, value: str) -> str:
    if not value:
        return value
    if os.path.isabs(value):
        return value
    return os.path.normpath(os.path.join(base_dir, value))


def _write_aws_profiles(credentials) -> Optional[str]:
    profiles = credentials.aws_profiles or {}
    if not profiles:
        return None
    home_dir = os.path.expanduser("~")
    aws_dir = os.path.join(home_dir, ".aws")
    try:
        os.makedirs(aws_dir, exist_ok=True)
    except OSError:
        aws_dir = os.path.join("/tmp", "chack-aws")
        os.makedirs(aws_dir, exist_ok=True)
    creds_path = os.path.join(aws_dir, "credentials")
    config_path = os.path.join(aws_dir, "config")

    with open(creds_path, "w", encoding="utf-8") as handle:
        for name, values in profiles.items():
            if not isinstance(values, dict):
                continue
            access_key = values.get("aws_access_key_id", "")
            secret_key = values.get("aws_secret_access_key", "")
            if not access_key or not secret_key:
                continue
            handle.write(f"[{name}]\n")
            handle.write(f"aws_access_key_id = {access_key}\n")
            handle.write(f"aws_secret_access_key = {secret_key}\n\n")

    with open(config_path, "w", encoding="utf-8") as handle:
        for name, values in profiles.items():
            if not isinstance(values, dict):
                continue
            region = values.get("aws_region", "") or values.get("region", "")
            if not region:
                continue
            profile_name = "default" if name == "default" else f"profile {name}"
            handle.write(f"[{profile_name}]\n")
            handle.write(f"region = {region}\n\n")

    return aws_dir


def export_env(config, config_path: str) -> None:
    base_dir = os.path.dirname(os.path.abspath(config_path))
    for key, value in (config.env or {}).items():
        if value is None:
            continue
        os.environ[str(key)] = str(value)

    creds = config.credentials
    if creds.aws_profiles:
        aws_dir = _write_aws_profiles(creds)
        if aws_dir:
            os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.path.join(aws_dir, "credentials")
            os.environ["AWS_CONFIG_FILE"] = os.path.join(aws_dir, "config")
    else:
        if creds.aws_access_key_id:
            os.environ["AWS_ACCESS_KEY_ID"] = creds.aws_access_key_id
        if creds.aws_secret_access_key:
            os.environ["AWS_SECRET_ACCESS_KEY"] = creds.aws_secret_access_key
        if creds.aws_region:
            os.environ["AWS_REGION"] = creds.aws_region

    if creds.aws_profile:
        os.environ["AWS_PROFILE"] = creds.aws_profile
    if not creds.aws_profiles and creds.aws_credentials_file:
        os.environ["AWS_SHARED_CREDENTIALS_FILE"] = _resolve_path(
            base_dir, creds.aws_credentials_file
        )
    if creds.stripe_api_key:
        os.environ["STRIPE_API_KEY"] = creds.stripe_api_key
    if creds.gcp_credentials_path:
        candidate = _resolve_path(base_dir, creds.gcp_credentials_path)
        if os.path.exists(candidate):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = candidate
        elif os.path.exists("/root/.gcp/credentials.json"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/root/.gcp/credentials.json"
        else:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = candidate
    if creds.gcp_quota_project:
        os.environ["GOOGLE_CLOUD_CPP_USER_PROJECT"] = creds.gcp_quota_project
    if creds.azure_app_id:
        os.environ["AZURE_APP_ID"] = creds.azure_app_id
    if creds.azure_sa_name:
        os.environ["AZURE_SA_NAME"] = creds.azure_sa_name
    if creds.azure_sa_secret_value:
        os.environ["AZURE_SA_SECRET_VALUE"] = creds.azure_sa_secret_value
    if creds.azure_tenant_id:
        os.environ["AZURE_TENANT_ID"] = creds.azure_tenant_id
    if creds.gh_token:
        os.environ["GH_TOKEN"] = creds.gh_token
    if creds.openai_api_key:
        os.environ["OPENAI_API_KEY"] = creds.openai_api_key
    if creds.openai_admin_key:
        os.environ["OPENAI_ADMIN_KEY"] = creds.openai_admin_key
    if creds.openai_org_id:
        os.environ["OPENAI_ORG_ID"] = creds.openai_org_id
    if creds.openai_org_ids:
        os.environ["OPENAI_ORG_IDS"] = ",".join([str(x) for x in creds.openai_org_ids if str(x).strip()])
    if config.tools.brave_api_key:
        os.environ["BRAVE_API_KEY"] = config.tools.brave_api_key
    if config.telegram.token:
        os.environ["TELEGRAM_BOT_TOKEN"] = config.telegram.token
    os.environ["CHACK_EXEC_TIMEOUT"] = str(config.tools.exec_timeout_seconds)
    os.environ["CHACK_EXEC_MAX_OUTPUT"] = str(config.tools.exec_max_output_chars)
