terraform {
  required_version = ">= 1.5.0"
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 4.0"
    }
  }
}

variable "grafana_url" {
  type        = string
  description = "Local Grafana URL as seen by the Terraform runner"
  default     = "http://127.0.0.1:3000"
}

variable "grafana_auth" {
  type        = string
  description = "Local demo basic auth in user:password format, or service account token"
  sensitive   = true
}

provider "grafana" {
  url  = var.grafana_url
  auth = var.grafana_auth
}

resource "grafana_folder" "demo" {
  title = "Operations - Terraform managed"
  uid   = "terraform-ops"
}

resource "grafana_folder_permission" "demo" {
  folder_uid = grafana_folder.demo.uid

  permissions {
    role       = "Viewer"
    permission = "View"
  }
  permissions {
    role       = "Editor"
    permission = "Edit"
  }
}

resource "grafana_data_source" "prometheus" {
  type = "prometheus"
  name = "Prometheus - demo"
  uid  = "prom-demo"
  url  = "http://prometheus:9090"
}

resource "grafana_data_source" "loki" {
  type = "loki"
  name = "Loki - demo"
  uid  = "loki-demo"
  url  = "http://loki:3100"
}

resource "grafana_dashboard" "demo" {
  folder      = grafana_folder.demo.uid
  config_json = file("${path.module}/../dashboards/app-overview.json")
  depends_on  = [grafana_data_source.prometheus, grafana_data_source.loki]
}

resource "grafana_rule_group" "api_errors" {
  name             = "API reliability"
  folder_uid       = grafana_folder.demo.uid
  org_id           = 1
  interval_seconds = 30

  rule {
    name           = "High 5xx error ratio"
    for            = "1m"
    condition      = "B"
    no_data_state  = "NoData"
    exec_err_state = "Error"
    annotations = {
      summary = "Synthetic API errors exceed 15% for one minute"
    }
    labels = {
      severity = "warning"
      service  = "demo-api"
    }

    data {
      ref_id         = "A"
      datasource_uid = grafana_data_source.prometheus.uid
      relative_time_range {
        from = 300
        to   = 0
      }
      model = jsonencode({
        refId         = "A"
        datasource    = { type = "prometheus", uid = grafana_data_source.prometheus.uid }
        expr          = "sum(rate(demo_http_requests_total{status=\"500\"}[1m])) / clamp_min(sum(rate(demo_http_requests_total[1m])), 0.001)"
        instant       = true
        intervalMs    = 1000
        maxDataPoints = 43200
      })
    }

    data {
      ref_id         = "B"
      datasource_uid = "__expr__"
      relative_time_range {
        from = 0
        to   = 0
      }
      model = jsonencode({
        type       = "math"
        expression = "$A > 0.15"
        refId      = "B"
        datasource = { type = "__expr__", uid = "__expr__" }
      })
    }
  }
}

output "dashboard_url" {
  value = "${var.grafana_url}/d/demo-overview"
}

# OPTIONAL: after generating dashboards/generated.json using Jsonnet,
# Terraform will also manage the generated dashboard.
resource "grafana_dashboard" "jsonnet" {
  count       = fileexists("${path.module}/../dashboards/generated.json") ? 1 : 0
  folder      = grafana_folder.demo.uid
  config_json = file("${path.module}/../dashboards/generated.json")
  depends_on  = [grafana_data_source.prometheus]
}
