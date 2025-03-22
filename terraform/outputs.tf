# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "The Juju application name"
  value       = juju_application.openfga.name
}

output "requires" {
  description = "The Juju integrations that the charm requires"
  value = {
    http-ingress = "http-ingress"
    grpc-ingress = "grpc-ingress"
    database     = "database"
    logging      = "logging"
    certificates = "certificates"
  }
}

output "provides" {
  description = "The Juju integrations that the charm provides"
  value = {
    openfga           = "openfga"
    metrics-endpoint  = "metrics-endpoint"
    grafana-dashboard = "grafana-dashboard"
  }
}
