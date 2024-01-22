# Charmed OpenFGA Operator

[![CharmHub Badge](https://charmhub.io/openfga-k8s/badge.svg)](https://charmhub.io/openfga-k8s)

## Description

This repository contains a [Juju Charm](https://charmhub.io/openfga-k8s) for deploying [OpenFGA](https://openfga.dev/) on Kubernetes.

## Usage

Bootstrap a [microk8s controller](https://juju.is/docs/olm/microk8s) using juju `3.2` and create a new Juju model:

```shell
juju add-model openfga
```

### Basic Usage
To deploy a single unit of OpenFGA using its default configuration.

```shell
juju deploy openfga-k8s --channel edge
juju deploy postgresql-k8s --channel edge
juju integrate postgresql-k8s:database openfga-k8s
juju run openfga-k8s/leader schema-upgrade --wait 30s
```

#### New `openfga` interface:

Current charm provides a library for the `openfga` relation interface. Your
application should define an interface in `metadata.yaml`:

```yaml
requires:
  openfga:
    interface: openfga
```

Then run
```shell
charmcraft fetch-lib charms.openfga_k8s.v0.openfga
```

Please read usage documentation about
[openfga](https://charmhub.io/openfga-k8s/libraries/openfga) library for
more information about how to enable PostgreSQL interface in your application.

Relations to new applications are supported via the `openfga` interface. To create a
relation:

```shell
juju integrate openfga-k8s application
```

To remove a relation:
```shell
juju remove-relation openfga-k8s application
```

#### `tls-certificates` interface:

The Charmed PostgreSQL Operator also supports TLS encryption on internal and external connections. To enable TLS:

```shell
# Deploy the TLS Certificates Operator.
juju deploy tls-certificates-operator --channel=edge
# Add the necessary configurations for TLS.
juju config tls-certificates-operator generate-self-signed-certificates="true" ca-common-name="Test CA"
# Enable TLS via relation.
juju relate openfga-k8s tls-certificates-operator
# Disable TLS by removing relation.
juju remove-relation openfga-k8s tls-certificates-operator
```

Note: The TLS settings shown here are for self-signed-certificates, which are not recommended for production clusters. The TLS Certificates Operator offers a variety of configurations. Read more on the TLS Certificates Operator [here](https://charmhub.io/tls-certificates-operator).

## Security
Security issues in the Charmed OpenFGA k8s Operator can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.

## Contributing
Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/openfga-operator/blob/main/CONTRIBUTING.md) for developer guidance.

## License
The OpenFGA k8s charm [is distributed](https://github.com/canonical/openfga-operator/blob/main/LICENSE) under the Apache Software License, version 2.0. It installs/operates/depends on [OpenFGA](https://github.com/openfga/openfga), which [is licensed](https://github.com/openfga/openfga/blob/main/LICENSE) under the Apache Software License, version 2.0.
