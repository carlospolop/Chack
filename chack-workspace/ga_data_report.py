#!/usr/bin/env python3
import os
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
]

def main():
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS is not set")
    property_id = os.environ.get("GA4_PROPERTY_ID")
    if not property_id:
        raise SystemExit("GA4_PROPERTY_ID is not set")

    creds = service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    client = BetaAnalyticsDataClient(credentials=creds)

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date="7daysAgo", end_date="today")],
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="activeUsers")],
        limit=10,
    )
    response = client.run_report(request)
    print("rows:")
    for row in response.rows:
        print(f"- {row.dimension_values[0].value}  activeUsers={row.metric_values[0].value}")

if __name__ == "__main__":
    main()
