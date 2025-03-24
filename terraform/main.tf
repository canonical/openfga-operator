/**
 * # Terraform Module for OpenFGA K8s Operator
 *
 * This is a Terraform module facilitating the deployment of the openfga-k8s
 * charm using the Juju Terraform provider.
 */

resource "juju_application" "openfga" {
  name        = var.app_name
  model       = var.model_name
  trust       = true
  config      = var.config
  constraints = var.constraints
  units       = var.units

  charm {
    name     = "openfga-k8s"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
}
