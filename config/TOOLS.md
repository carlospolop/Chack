#### Agent Tools

These are the **tool functions** the agent can call (exposed via `chack.tools.Toolset`).
They are enabled/disabled in `config/chack.yaml` under the `tools:` section.

- **`exec`**
	- Runs a local shell command inside the container/host environment and returns combined stdout/stderr.
	- The outout will be trimmed if it's bigger than an allowed mx length. If that happens, please re-execute using grep or similar to filter the data you are actually interested in.
	- You can use this for example to access APIs and call intalled tools so use `grep/jq` to filter results, to use `curl`(even with different UAs) to access web pages...

- **`duckduckgo_search`**
	- Web search via DuckDuckGo HTML endpoint; returns a short list of results. Use it to confirm facts or check any web information relevant to your tasks (info about commands, installations, libraries...)
	- It's super important you verify your responses if you are not super sure of something, specially if there was a chance that it could have changed from the time you were trained. Always verify information about APIs, data, facts searching int he web

- **`brave_search`**
	- Web search via Brave Search API; returns a short list of results. Use it to confirm facts or check any web information relevant to your tasks (info about commands, installations, libraries...)
	- It's super important you verify your responses if you are not super sure of something, specially if there was a chance that it could have changed from the time you were trained. Always verify information about APIs, data, facts searching int he web

#### Installed CLIs

These are command-line tools expected to be available to the agent in the container environment:

- **AWS CLI**: `aws`
	- Typical uses: verify identity (`sts get-caller-identity`), list resources, check config.
	- Credentials come from env vars or from the /root/.aws/credentials file with different profiles on it.
	- When requested to check something in AWS, if there are more than 1 set of credentials check yourself which ones you think you should be using.

- **Google Cloud SDK**: `gcloud` (and usually `bq`)
	- Typical uses: auth/status, list resources, enable services, interact with BigQuery.
	- Credentials are provided via `GOOGLE_APPLICATION_CREDENTIALS`.

- **Stripe CLI**: `stripe`
	- Typical uses: quick API checks (whoami/status), listen for webhooks, inspect events.
	- API auth is typically via `STRIPE_API_KEY` (never print it).

- **Azure CLI**: `az`
	- Typical uses: auth via service principal, list resources, storage account operations.
	- Auth env vars are provided (see below).

- **GitHub CLI**: `gh`
	- Typical uses: repo operations, issues/PRs, auth for git.
	- Auth is typically via `GH_TOKEN`.

- **GA Python venv**: `/opt/ga-venv/bin` (on `PATH`)
	- A Python environment intended for Google Analytics / related automation.

- **Terraform CLI**: `terraform`
	- Terraform cli so you can check the syntax of terraform changes. Never fo a terraform apply but use it like `terraform init` and `terraform validate` to check for syntax errors.


If unsure whether a CLI exists, verify first:
- `aws --version`
- `gcloud --version`
- `stripe version`
- `az version`
- `gh --version`
- `terraform --version`

### Credentials & Safety

- Treat all env vars like secrets unless explicitly public.
- Never paste API keys/tokens/credentials in chat.
- If command output includes credentials, redact them before responding.

Common env vars used here:
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`´
	- AWS credentials could also be located in the /root/.aws/credentials file giving you probably access to different AWS accounts with different profiles
	- If the credentials from the /root/.aws/credentials file are used, you need to use the needed profile with the "--profile" argument in the "aws" cli.
- `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_CPP_USER_PROJECT`
- `AZURE_APP_ID`, `AZURE_SA_SECRET_VALUE`, `AZURE_TENANT_ID`, `AZURE_SA_NAME`
- `GH_TOKEN`
- `STRIPE_API_KEY`
- `OPENAI_API_KEY`, `OPENAI_ADMIN_KEY`

### Org-wide Listing Cheatsheet

- **AWS: list all accounts in an AWS Organization**
	- Requires Organizations access in the management account (or a delegated admin with org permissions).
	- Command:
	  - `aws organizations list-accounts --output json`
	- If you must use a specific profile:
	  - `aws organizations list-accounts --output json --profile <profile>`

- **GCP: list all projects in a GCP Organization**
	- Requires `resourcemanager.projects.list` on the org (e.g., Viewer at org level).
	- Command (list all projects under an org):
	  - `gcloud projects list --filter="parent.type=organization parent.id=ORG_ID" --format=json`
	- If org ID is unknown, list organizations first:
	  - `gcloud organizations list --format=json`

### GCP Billing Data (BigQuery)

Billing static info is stored in BigQuery:
- **Project:** `billing-static-info-no-delete`
- **Dataset:** `billinginfo`

When asked about billing data, prefer querying BigQuery (via `bq` if available, or `gcloud` + BigQuery APIs) rather than guessing.

### Google Analytics Examples (Scripts)

This workspace includes two small scripts showing how to access Google Analytics with a service account:

- `ga_admin_list.py` (GA Admin API)
	- Lists Analytics **accounts** and **properties** the service account can see.

- `ga_data_report.py` (GA4 Data API)
	- Runs a simple GA4 report (last 7 days) with dimension `date` and metric `activeUsers`.

Notes:
- These use the `analytics.readonly` scope.

Location inside the container:
- `/app/chack-workspace/ga_admin_list.py`
- `/app/chack-workspace/ga_data_report.py`

You can create your own scripts to access any requested google analytics data if needed.


### OpenAI Org Costs (Script)

- `openai_org_costs.py`
	- Fetches org-level costs and usage.
	- Uses `OPENAI_ADMIN_KEY` (preferred) or `OPENAI_API_KEY`, plus optional `OPENAI_ORG_ID` or `OPENAI_ORG_IDS` (admin privileges may be required for org endpoints).
	- Defaults to last 30 days if no dates are provided.
	- Commands:
	  - Costs: `python /app/chack-workspace/openai_org_costs.py costs --start-date YYYY-MM-DD --end-date YYYY-MM-DD`
	  - Costs total: `python /app/chack-workspace/openai_org_costs.py costs --start-date YYYY-MM-DD --end-date YYYY-MM-DD --total`
	  - Costs by project: `python /app/chack-workspace/openai_org_costs.py costs --start-date YYYY-MM-DD --end-date YYYY-MM-DD --by-project`
	  - Usage: `python /app/chack-workspace/openai_org_costs.py usage --endpoint completions --start-date YYYY-MM-DD --end-date YYYY-MM-DD`
	  - Usage (by api key): `python /app/chack-workspace/openai_org_costs.py usage --endpoint completions --api-key-ids key_...`
	  - Usage (grouped): `python /app/chack-workspace/openai_org_costs.py usage --endpoint completions --group-by model,project_id,api_key_id --start-date YYYY-MM-DD --end-date YYYY-MM-DD`
	  - List projects: `python /app/chack-workspace/openai_org_costs.py projects`
	  - List project keys: `python /app/chack-workspace/openai_org_costs.py project-keys --project-id PROJECT_ID`
	  - List admin keys: `python /app/chack-workspace/openai_org_costs.py admin-keys`
	  - Multiple orgs: set `OPENAI_ORG_IDS=org_...,org_...` or pass `--org-ids org_...,org_...`


### Main Github repos

- In `HackTricks-Training/wiki-infrastructure` you can find the terraform infrastructure of the AWS account `wiki` and all the code of the lambda tools
- In `hacktricks-training/platform` you can find all the terraform infra of the hacktricks training platform
- In `HackTricks-Training/ARTE-Labs-TF`, `**/ARTA-Labs-TF`, `**/GRTE-Labs-TF`, `**/GRTA-Labs-TF`, `**/AzRTE-Labs-TF`, `**/AzRTA-Labs-TF` labs you have the terraform of the labs of those certifications
- In other `HackTricks-Training` repos you can find the exam terraforms, the walkthroughs of the labs and more repos related to HT Training

- In `HackTricks-wiki/hacktricks` you have the book of HackTricks
- In `HackTricks-wiki/hacktricks-cloud` you have the book of HackTricks Cloud
- In `HackTricks-wiki/hacktricks-feed` you have the agent bots that feeds hacktricks, hacktricks cloud and hacktricks Feed groups

- In `peass-ng/PEASS-ng` you have the repo of the PEASS-ng tools
- In `peass-ng/CloudPEASS` you have the repo of the cloudpeass tools
- In `peass-ng/Blue-CloudPEASS` you have the repo of the Blue-CloudPEASS tools

- In `carlospolop/MalwareWorld` you have the repo of Malwareworld
- In `carlospolop/PurplePanda` you have the repo of PurplePanda
- In `carlospolop/**` you can find other repos related to carlospolop

- In `AI-Gents/dashboard` you have the dashboard (front-end) of NaxusAI
- In `AI-Gents/Infra` you have the terraform infra of NaxusAI
- In `AI-Gents/backend` you have the backend (API) of NaxusAI
- In `AI-Gents/AISecurityAuditor` you have the main engine/agents of NaxusAI

- Remember if you are asked to do a change better create a PR into the Repo than merging directly into main/master.
- If you find a repo already cloned, always make sure you are working with the latest code from the main/master branch.