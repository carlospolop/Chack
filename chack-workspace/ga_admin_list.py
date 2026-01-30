#!/usr/bin/env python3
import os
from google.oauth2 import service_account
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
]

def main():
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS is not set")
    creds = service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    client = AnalyticsAdminServiceClient(credentials=creds)

    accounts = list(client.list_accounts())
    print(f"accounts: {len(accounts)}")
    for acc in accounts:
        print(f"- {acc.name}  {acc.display_name}")

    properties = []
    for acc in accounts:
        req = {"filter": f"parent:{acc.name}"}
        for prop in client.list_properties(request=req):
            properties.append(prop)
    print(f"properties: {len(properties)}")
    for prop in properties:
        print(f"- {prop.name}  {prop.display_name}")

if __name__ == "__main__":
    main()
