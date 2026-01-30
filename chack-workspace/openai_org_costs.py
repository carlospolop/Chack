#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
from typing import Optional, Sequence

import requests


USAGE_ENDPOINTS = [
    "completions",
    "images",
    "audio",
    "embeddings",
    "moderations",
    "vector_stores",
    "code_interpreter_sessions",
]


def _parse_date(value: str) -> dt.datetime:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def _to_unix_seconds(value: dt.datetime) -> int:
    return int(value.replace(tzinfo=dt.timezone.utc).timestamp())


def _default_range() -> tuple[int, int]:
    end = dt.datetime.now(tz=dt.timezone.utc)
    start = end - dt.timedelta(days=30)
    return _to_unix_seconds(start), _to_unix_seconds(end)


def _get_headers(api_key: str, org_id: Optional[str]) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"}
    if org_id:
        headers["OpenAI-Organization"] = org_id
    return headers


def _list_arg(value: Optional[str]) -> Optional[Sequence[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_orgs(org_id: Optional[str], org_ids: Optional[str]) -> tuple[Optional[str], Sequence[str]]:
    if org_id:
        return org_id, []
    env_org_ids = os.environ.get("OPENAI_ORG_IDS")
    resolved = _list_arg(org_ids) or _list_arg(env_org_ids) or []
    return None, resolved


def _request(base_url: str, path: str, api_key: str, org_id: Optional[str], params: dict) -> dict:
    url = base_url.rstrip("/") + path
    resp = requests.get(url, headers=_get_headers(api_key, org_id), params=params, timeout=30)
    if resp.status_code != 200:
        raise SystemExit(f"ERROR: {resp.status_code} {resp.text[:500]}")
    return resp.json()


def _paginate(base_url: str, path: str, api_key: str, org_id: Optional[str], params: dict) -> dict:
    merged = {"object": None, "data": [], "has_more": False, "next_page": None}
    page_params = dict(params)
    while True:
        data = _request(base_url, path, api_key, org_id, page_params)
        merged["object"] = merged["object"] or data.get("object")
        merged["data"].extend(data.get("data", []))
        merged["has_more"] = bool(data.get("has_more"))
        merged["next_page"] = data.get("next_page")
        if not merged["has_more"] or not merged["next_page"]:
            break
        page_params["page"] = merged["next_page"]
    return merged


def _sum_costs(costs_data: dict) -> float:
    total = 0.0
    for bucket in costs_data.get("data", []):
        for result in bucket.get("results", []):
            amount = result.get("amount", {})
            value = amount.get("value")
            if value is not None:
                total += float(value)
    return total


def _with_time_range(args) -> dict:
    if args.start_date and args.end_date:
        start = _to_unix_seconds(_parse_date(args.start_date))
        end = _to_unix_seconds(_parse_date(args.end_date))
    else:
        start, end = _default_range()
    return {"start_time": start, "end_time": end, "interval": args.interval}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query OpenAI org costs and usage endpoints."
    )
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_API_BASE", "https://api.openai.com"))
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_ADMIN_KEY") or os.environ.get("OPENAI_API_KEY"),
        help="Defaults to OPENAI_ADMIN_KEY, then OPENAI_API_KEY.",
    )
    parser.add_argument("--org-id", default=os.environ.get("OPENAI_ORG_ID") or os.environ.get("OPENAI_ORGANIZATION"))
    parser.add_argument(
        "--org-ids",
        help="Comma-separated org IDs. If provided, runs the command for each org and returns a map.",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    costs = sub.add_parser("costs", help="Fetch org costs.")
    costs.add_argument("--start-date", help="YYYY-MM-DD (inclusive)")
    costs.add_argument("--end-date", help="YYYY-MM-DD (exclusive)")
    costs.add_argument("--interval", default="1d", help="Interval, default 1d")
    costs.add_argument("--project-ids", help="Comma-separated project IDs to filter")
    costs.add_argument(
        "--api-key-ids",
        help="Not supported by Costs API; use 'usage' with api_key_ids instead.",
    )
    costs.add_argument(
        "--group-by",
        help="Comma-separated fields to group costs by (e.g., project_id,line_item).",
    )
    costs.add_argument(
        "--total",
        action="store_true",
        help="Print total cost value (sum of line_items.value) instead of raw JSON.",
    )
    costs.add_argument(
        "--by-project",
        action="store_true",
        help="Print cost totals grouped by project_id (JSON).",
    )

    usage = sub.add_parser("usage", help="Fetch org usage for a specific endpoint.")
    usage.add_argument("--endpoint", required=True, choices=USAGE_ENDPOINTS)
    usage.add_argument("--start-date", help="YYYY-MM-DD (inclusive)")
    usage.add_argument("--end-date", help="YYYY-MM-DD (exclusive)")
    usage.add_argument("--interval", default="1d", help="Interval, default 1d")
    usage.add_argument("--project-ids", help="Comma-separated project IDs to filter")
    usage.add_argument("--user-ids", help="Comma-separated user IDs to filter")
    usage.add_argument("--api-key-ids", help="Comma-separated API key IDs to filter")
    usage.add_argument("--models", help="Comma-separated model IDs to filter")
    usage.add_argument(
        "--group-by",
        help="Comma-separated fields to group usage by (e.g., model,project_id,api_key_id).",
    )

    sub.add_parser("projects", help="List org projects.")

    project_keys = sub.add_parser("project-keys", help="List API keys for a project.")
    project_keys.add_argument("--project-id", required=True)

    sub.add_parser("admin-keys", help="List admin API keys for the org.")

    args = parser.parse_args()

    if not args.api_key:
        print("OPENAI_API_KEY is not set.")
        return 1

    org_id, org_ids = _resolve_orgs(args.org_id, args.org_ids)

    if args.cmd == "costs":
        if args.api_key_ids:
            raise SystemExit(
                "Costs API does not support api_key_ids. Use: "
                "`usage --endpoint completions --api-key-ids ...` (or other endpoint)."
            )
        params = _with_time_range(args)
        project_ids = _list_arg(args.project_ids)
        if project_ids:
            params["project_ids"] = project_ids
        group_by = _list_arg(args.group_by)
        if group_by:
            params["group_by"] = group_by
        if org_ids:
            payload = {}
            for oid in org_ids:
                data = _paginate(args.base_url, "/v1/organization/costs", args.api_key, oid, params)
                if args.by_project:
                    totals = {}
                    for bucket in data.get("data", []):
                        for result in bucket.get("results", []):
                            pid = result.get("project_id") or "unknown"
                            pname = result.get("project_name") or ""
                            key = f"{pid}|{pname}".rstrip("|")
                            amount = result.get("amount", {}).get("value")
                            if amount is not None:
                                totals[key] = totals.get(key, 0.0) + float(amount)
                    payload[oid] = totals
                elif args.total:
                    payload[oid] = _sum_costs(data)
                else:
                    payload[oid] = data
            if args.total:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(json.dumps(payload, indent=2))
        else:
            data = _paginate(args.base_url, "/v1/organization/costs", args.api_key, org_id, params)
            if args.by_project:
                totals = {}
                for bucket in data.get("data", []):
                    for result in bucket.get("results", []):
                        pid = result.get("project_id") or "unknown"
                        pname = result.get("project_name") or ""
                        key = f"{pid}|{pname}".rstrip("|")
                        amount = result.get("amount", {}).get("value")
                        if amount is not None:
                            totals[key] = totals.get(key, 0.0) + float(amount)
                print(json.dumps(totals, indent=2, sort_keys=True))
            elif args.total:
                print(f"{_sum_costs(data):.2f}")
            else:
                print(json.dumps(data, indent=2))
        return 0

    if args.cmd == "usage":
        params = _with_time_range(args)
        for name, value in [
            ("project_ids", _list_arg(args.project_ids)),
            ("user_ids", _list_arg(args.user_ids)),
            ("api_key_ids", _list_arg(args.api_key_ids)),
            ("models", _list_arg(args.models)),
        ]:
            if value:
                params[name] = value
        group_by = _list_arg(args.group_by)
        if group_by:
            params["group_by"] = group_by
        if org_ids:
            payload = {}
            for oid in org_ids:
                data = _paginate(
                    args.base_url,
                    f"/v1/organization/usage/{args.endpoint}",
                    args.api_key,
                    oid,
                    params,
                )
                payload[oid] = data
            print(json.dumps(payload, indent=2))
        else:
            data = _paginate(
                args.base_url,
                f"/v1/organization/usage/{args.endpoint}",
                args.api_key,
                org_id,
                params,
            )
            print(json.dumps(data, indent=2))
        return 0

    if args.cmd == "projects":
        if org_ids:
            payload = {}
            for oid in org_ids:
                data = _request(args.base_url, "/v1/organization/projects", args.api_key, oid, {})
                payload[oid] = data
            print(json.dumps(payload, indent=2))
        else:
            data = _request(args.base_url, "/v1/organization/projects", args.api_key, org_id, {})
            print(json.dumps(data, indent=2))
        return 0

    if args.cmd == "project-keys":
        if org_ids:
            raise SystemExit("project-keys requires a single org. Use --org-id or OPENAI_ORG_ID.")
        data = _request(
            args.base_url,
            f"/v1/organization/projects/{args.project_id}/api_keys",
            args.api_key,
            org_id,
            {},
        )
        print(json.dumps(data, indent=2))
        return 0

    if args.cmd == "admin-keys":
        if org_ids:
            payload = {}
            for oid in org_ids:
                data = _request(args.base_url, "/v1/organization/admin_api_keys", args.api_key, oid, {})
                payload[oid] = data
            print(json.dumps(payload, indent=2))
        else:
            data = _request(args.base_url, "/v1/organization/admin_api_keys", args.api_key, org_id, {})
            print(json.dumps(data, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
