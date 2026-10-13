#!/usr/bin/env python3
"""Grafana API lab using separate 'api-' UIDs to avoid Terraform ownership conflicts.

Usage:
  python api/manage_grafana.py provision
  python api/manage_grafana.py alert
  python api/manage_grafana.py inspect

Requires requests and a Grafana 12.x instance. The legacy /api endpoints are
still functional in Grafana 13, but new /apis endpoints are preferred going forward.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

URL = os.getenv("GRAFANA_URL", "http://127.0.0.1:3000").rstrip("/")
TOKEN = os.getenv("GRAFANA_TOKEN")
FOLDER_UID = "api-ops"
DATASOURCE_UID = "api-prom"
ALERT_UID = "api-error-alert"

s = requests.Session()
s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
if TOKEN:
    s.headers["Authorization"] = f"Bearer {TOKEN}"
else:
    s.auth = (os.getenv("GRAFANA_USER", "admin"), os.getenv("GRAFANA_PASSWORD", "admin"))


def req(method, endpoint, **kwargs):
    result = s.request(method, URL + endpoint, timeout=10, **kwargs)
    if result.status_code >= 400:
        raise RuntimeError(f"{method} {endpoint}: {result.status_code} {result.text[:500]}")
    return result.json() if result.content else None


def maybe_get(path):
    res = s.get(URL + path, timeout=10)
    if res.status_code == 404:
        return None
    res.raise_for_status()
    return res.json()


def provision():
    # Create or verify a dedicated API-managed folder.
    if not maybe_get(f"/api/folders/{FOLDER_UID}"):
        req("POST", "/api/folders", json={"uid": FOLDER_UID, "title": "Operations - API managed"})
    print("Folder exists:", FOLDER_UID)

    source = {
        "uid": DATASOURCE_UID,
        "name": "Prometheus - API demo",
        "type": "prometheus",
        "access": "proxy",
        "url": "http://prometheus:9090",
    }
    if maybe_get(f"/api/datasources/uid/{DATASOURCE_UID}"):
        req("PUT", f"/api/datasources/uid/{DATASOURCE_UID}", json=source)
    else:
        req("POST", "/api/datasources", json=source)
    print("Data source exists:", DATASOURCE_UID)

    # This is a replace-all API: do not use casually against production folders.
    req("POST", f"/api/folders/{FOLDER_UID}/permissions", json={
        "items": [
            {"role": "Viewer", "permission": 1},
            {"role": "Editor", "permission": 2},
        ]
    })
    print("Folder permissions set")

    dashboard = json.loads((Path(__file__).resolve().parents[1] / "dashboards" / "app-overview.json").read_text())
    dashboard["uid"] = "api-dashboard"
    dashboard["title"] = "Demo API - deployed via HTTP API"
    dashboard["id"] = None
    dashboard["version"] = 0
    for panel in dashboard["panels"]:
        if panel["datasource"]["type"] == "prometheus":
            panel["datasource"]["uid"] = DATASOURCE_UID
    # The API-managed dashboard uses only Prometheus panels;
    # the Loki panel is owned and configured by the Terraform demo.
    dashboard["panels"] = [p for p in dashboard["panels"] if p["datasource"]["type"] == "prometheus"]
    req("POST", "/api/dashboards/db", json={"dashboard": dashboard, "folderUid": FOLDER_UID, "overwrite": True, "message": "Automated API dashboard deployment"})
    print("Dashboard created/updated: /d/api-dashboard")


def provision_alert():
    provision()
    payload = {
        "uid": ALERT_UID,
        "title": "API managed high 5xx ratio",
        "ruleGroup": "API automation",
        "folderUID": FOLDER_UID,
        "orgId": 1,
        "for": "1m",
        "noDataState": "NoData",
        "execErrState": "Error",
        "condition": "B",
        "labels": {"service": "demo-api", "severity": "warning"},
        "annotations": {"summary": "HTTP 5xx ratio higher than 15%"},
        "data": [
            {
                "refId": "A",
                "relativeTimeRange": {"from": 300, "to": 0},
                "datasourceUid": DATASOURCE_UID,
                "model": {
                    "refId": "A", "datasource": {"type": "prometheus", "uid": DATASOURCE_UID},
                    "expr": 'sum(rate(demo_http_requests_total{status="500"}[1m])) / clamp_min(sum(rate(demo_http_requests_total[1m])), 0.001)',
                    "instant": True, "intervalMs": 1000, "maxDataPoints": 43200,
                },
            },
            {
                "refId": "B",
                "relativeTimeRange": {"from": 0, "to": 0},
                "datasourceUid": "__expr__",
                "model": {"type": "math", "expression": "$A > 0.15", "refId": "B", "datasource": {"type": "__expr__", "uid": "__expr__"}},
            },
        ],
    }
    if maybe_get(f"/api/v1/provisioning/alert-rules/{ALERT_UID}"):
        req("PUT", f"/api/v1/provisioning/alert-rules/{ALERT_UID}", json=payload)
    else:
        req("POST", "/api/v1/provisioning/alert-rules", json=payload)
    print("Alert created/updated:", ALERT_UID)


def inspect():
    for name, route in (
        ("health", "/api/health"),
        ("folders", "/api/folders"),
        ("data sources", "/api/datasources"),
        ("alert rules", "/api/v1/provisioning/alert-rules"),
        ("API folder permissions", f"/api/folders/{FOLDER_UID}/permissions"),
    ):
        print(f"\n--- {name} ---")
        print(json.dumps(req("GET", route), indent=2)[:2500])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["provision", "alert", "inspect"])
    args = parser.parse_args()
    try:
        {"provision": provision, "alert": provision_alert, "inspect": inspect}[args.command]()
    except (requests.RequestException, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
