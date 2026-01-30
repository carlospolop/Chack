#!/usr/bin/env sh
set -e

CONFIG_PATH="${CHACK_CONFIG:-/app/config/chack.yaml}"

if [ -f "$CONFIG_PATH" ]; then
  eval "$(python - <<'PY'
import os, shlex
from chack.config import load_config
from chack.env_utils import export_env

config_path = os.environ.get("CHACK_CONFIG", "/app/config/chack.yaml")
config = load_config(config_path)
export_env(config, config_path)

keys = {
  "OPENAI_API_KEY","OPENAI_ADMIN_KEY","OPENAI_ORG_ID","TELEGRAM_BOT_TOKEN","BRAVE_API_KEY","AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY",
  "AWS_REGION","AWS_PROFILE","AWS_SHARED_CREDENTIALS_FILE","AWS_CONFIG_FILE","GOOGLE_APPLICATION_CREDENTIALS",
  "GOOGLE_CLOUD_CPP_USER_PROJECT","AZURE_APP_ID","AZURE_SA_NAME","AZURE_SA_SECRET_VALUE","AZURE_TENANT_ID",
  "GH_TOKEN","STRIPE_API_KEY",
}
for key in keys:
    value = os.environ.get(key)
    if value:
        print(f"export {key}={shlex.quote(value)}")
PY
)"
fi

if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ] && [ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
  gcloud auth activate-service-account --key-file "$GOOGLE_APPLICATION_CREDENTIALS" >/tmp/gcloud-auth.log 2>&1 || true
  if [ -n "$GOOGLE_CLOUD_CPP_USER_PROJECT" ]; then
    gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_CPP_USER_PROJECT" >/tmp/gcloud-quota.log 2>&1 || true
    gcloud config set billing/quota_project "$GOOGLE_CLOUD_CPP_USER_PROJECT" >/tmp/gcloud-quota.log 2>&1 || true
  fi
fi

if [ -n "$AZURE_APP_ID" ] && [ -n "$AZURE_SA_SECRET_VALUE" ] && [ -n "$AZURE_TENANT_ID" ]; then
  az login --service-principal -u "$AZURE_APP_ID" -p "$AZURE_SA_SECRET_VALUE" --tenant "$AZURE_TENANT_ID" >/tmp/az-auth.log 2>&1 || true
fi

if [ -n "$GH_TOKEN" ]; then
  : > /tmp/gh-auth.log
  GH_TOKEN_VALUE="$GH_TOKEN"
  unset GH_TOKEN
  if [ ! -f /root/.config/gh/hosts.yml ]; then
    printf "%s" "$GH_TOKEN_VALUE" | gh auth login --with-token >>/tmp/gh-auth.log 2>&1 || true
  fi
  if ! gh auth status -h github.com >>/tmp/gh-auth.log 2>&1; then
    echo "WARNING: gh auth failed; see /tmp/gh-auth.log" >&2
  fi
  gh auth setup-git >>/tmp/gh-auth.log 2>&1 || true
  git config --global user.name "chack" >>/tmp/gh-auth.log 2>&1 || true
  git config --global user.email "chack@hacktricks.bot" >>/tmp/gh-auth.log 2>&1 || true
  export GH_TOKEN="$GH_TOKEN_VALUE"
else
  echo "WARNING: GH_TOKEN is not set; gh will be unauthenticated." >&2
fi

exec "$@"
