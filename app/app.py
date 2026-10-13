"""Synthetic application: publishes Prometheus metrics and demo logs to Loki.

Direct Loki push keeps the one-day lab small; use Grafana Alloy or an OTLP
collector for production log collection. Never push sensitive log content.
"""
import json
import os
import random
import time
from datetime import datetime, timezone

import requests
from prometheus_client import Counter, Gauge, Histogram, start_http_server

REQUESTS = Counter("demo_http_requests_total", "Synthetic HTTP requests", ["status"])
DURATION = Histogram("demo_http_request_duration_seconds", "Synthetic request duration")
QUEUE = Gauge("demo_queue_depth", "Synthetic requests waiting")


def main():
    start_http_server(8000)
    failure_rate = float(os.getenv("FAILURE_RATE", "0.02"))
    if not 0 <= failure_rate <= 1:
        raise ValueError("FAILURE_RATE must be between 0 and 1")
    loki_url = os.getenv("LOKI_URL", "http://loki:3100/loki/api/v1/push")
    print(f"Metrics on :8000/metrics; simulated failure rate={failure_rate}", flush=True)
    while True:
        status = "500" if random.random() < failure_rate else "200"
        duration = random.uniform(.25, .9) if status == "500" else random.uniform(.01, .14)
        REQUESTS.labels(status=status).inc()
        DURATION.observe(duration)
        QUEUE.set(random.randint(0, 14))
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "error" if status == "500" else "info",
            "status": int(status),
            "message": "Synthetic GET /api/orders",
            "duration_ms": round(duration * 1000, 1),
        }
        print(json.dumps(event), flush=True)
        log_record = {"streams": [{
            "stream": {"app": "demo", "level": event["level"]},
            "values": [[str(time.time_ns()), json.dumps(event)]],
        }]}
        try:
            response = requests.post(loki_url, json=log_record, timeout=2)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Loki temporarily unavailable: {exc}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
