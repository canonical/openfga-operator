# Charmed OpenFGA Operator

[![CharmHub Badge](https://charmhub.io/openfga-k8s/badge.svg)](https://charmhub.io/openfga-k8s)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
[![License](https://img.shields.io/github/license/canonical/openfga-operator?label=License)](https://github.com/canonical/openfga-operator/blob/main/LICENSE)

[![Continuous Integration Status](https://github.com/canonical/openfga-operator/actions/workflows/on_push.yaml/badge.svg?branch=main)](https://github.com/canonical/openfga-operator/actions?query=branch%3Amain)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196.svg)](https://conventionalcommits.org)

## Description

This repository contains a [Juju Charm](https://charmhub.io/openfga-k8s) for
deploying [OpenFGA](https://openfga.dev/) on Kubernetes.

## Usage

Bootstrap a [microk8s controller](https://juju.is/docs/olm/microk8s) using
juju `3.2` and create a new Juju model:

```shell
juju add-model openfga
```

### Basic Usage

To deploy a single unit of OpenFGA using its default configuration.

```shell
juju deploy openfga-k8s --channel edge
juju deploy postgresql-k8s --channel edge
juju integrate postgresql-k8s:database openfga-k8s
```

#### `openfga` interface

Current charm provides a library for the `openfga` integration interface. Your
application should define an interface in `metadata.yaml`:

```yaml
requires:
  openfga:
    interface: openfga
```

Then run

```shell
charmcraft fetch-lib charms.openfga_k8s.v1.openfga
```

Please read usage documentation
about [openfga](https://charmhub.io/openfga-k8s/libraries/openfga) library for
more information about how to enable PostgreSQL interface in your application.

Integrations to new applications are supported via the `openfga` interface. To
create an integration:

```shell
juju integrate openfga-k8s <application>
```

To remove an integration:

```shell
juju remove-relation openfga-k8s <application>
```

#### `tls-certificates` interface

The Charmed PostgreSQL Operator also supports TLS encryption on internal and
external connections. To enable TLS:

```shell
# Deploy the TLS Certificates Operator.
juju deploy tls-certificates-operator --channel=edge
# Add the necessary configurations for TLS.
juju config tls-certificates-operator generate-self-signed-certificates="true" ca-common-name="Test CA"
# Enable TLS via integration.
juju integrate openfga-k8s tls-certificates-operator
# Disable TLS by removing integration.
juju remove-relation openfga-k8s tls-certificates-operator
```

Note: The TLS settings shown here are for self-signed-certificates, which are
not recommended for production clusters. The TLS Certificates Operator offers a
variety of configurations. Read more on the TLS Certificates
Operator [here](https://charmhub.io/tls-certificates-operator).

## Observability

This OpenFGA operator integrates
with [Canonical Observability Stack (COS)](https://charmhub.io/topics/canonical-observability-stack)
bundle.
It comes with a Grafana dashboard and Loki and Prometheus alert rules for basic
common scenarios. To integrate with the COS bundle, after
you [deploy it](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s#heading--deploy-the-cos-lite-bundle),
you can run:

```shell
juju integrate openfga:grafana-dashboard grafana:grafana-dashboard
juju integrate openfga:metrics-endpoint prometheus:metrics-endpoint
juju integrate loki:logging openfga:log-proxy
```

## Security

Security issues in the Charmed OpenFGA k8s Operator can be reported
through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File).
Please do not file GitHub issues about security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on
enhancements to this charm following best practice guidelines,
and [CONTRIBUTING.md](https://github.com/canonical/openfga-operator/blob/main/CONTRIBUTING.md)
for developer guidance.

## License

The OpenFGA k8s
charm [is distributed](https://github.com/canonical/openfga-operator/blob/main/LICENSE)
under the Apache Software License, version 2.0. It installs/operates/depends
on [OpenFGA](https://github.com/openfga/openfga),
which [is licensed](https://github.com/openfga/openfga/blob/main/LICENSE) under
the Apache Software License, version 2.0.
