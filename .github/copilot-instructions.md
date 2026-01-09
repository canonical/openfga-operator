# Agent instructions for OpenFGA charm development

This document defines expectations and boundaries for **automated agents** (AI
coding assistants) contributing to this repository.

The goal is to enable helpful, high-quality contributions while ensuring that
the
code remains maintainable, secure, and aligned with the project's standards.

## Repository Context

This repository contains a **Juju Kubernetes operator (charm)** for running
**OpenFGA** on Kubernetes.

The charmed operator is written in **Python** and uses
the [Juju Operator Framework](https://github.com/canonical/operator), with:

- Supported Python version `3.12`
- Main charm logic in `src/`
- Charm library logic in `lib/charms/openfga_k8s`
- Unit and integration tests in `tests/`
- Terraform configurations in `terraform/`
- CI and release workflows in `.github/workflows/`

## Allowed Contributions with Human Review

Agents may propose and contribute to following:

- Charm logic in `src/` and `lib/charms/openfga_k8s`
- Unit and integration tests in `tests/`
- Terraform configurations in `terraform/`
- CI and release workflows in `.github/workflows/`
- Documentation (`README.md` and `CONTRIBUTING.md`)

**Note**: Agents **MUST NOT** directly merge pull requests. All contributions
**MUST** be reviewed and approved by a human maintainer.

## Restricted Contributions

Agents **MUST NOT** contribute to following:

- Charmcraft configuration files (e.g., `charmcraft.yaml`)
- Renovate managed dependency updates according to `renovate.json`
- Dependent charm library in `lib/charms/` except the owned `openfga_k8s`
  library in `lib/charms/openfga_k8s`
- Cross-cutting refactors affecting multiple components without explicit human
  guidance

## Contribution Guidelines

Agents **MUST** adhere to the following guidelines.

### Coding Style and Conventions

- Follow [PEP 8](https://peps.python.org/pep-0008/) for Python code
- Use type hints as per [PEP 484](https://peps.python.org/pep-0484/), but also
  adopt any new `typing` features in Python 3.12. For example, `list[str]`
  instead of `List[str]`, etc.
- Prefer EAFP (Easier to Ask Forgiveness than Permission) over LBYL (Look Before
  You Leap) in Python code
- Respect existing naming conventions and architectural patterns in the codebase
- Follow the SOLID principles of object-oriented design, but avoid
  over-engineering

### Charm-specific Design Patterns

This charmed operator follows a specific design pattern developed
by the Identity Team in Canonical. The bottom line idea is to separate the logic
from the `charm.py` by implementing the following layers:

- Orchestration layer (in `charm.py`): responsible for handling Juju events and
  orchestrating the data flow between the different components
- Abstraction layer (in `configs.py`, `integrations.py`, `secret.py`, and
  `services.py`): responsible for abstracting Juju-specific concepts in order to
  provide clean interfaces for the orchestration layer to use
- Infrastructure layer (in `cli.py` and `clients.py`): responsible for providing
  supporting functionalities to the upper layers, such as interacting with Juju,
  external services, and third-party libraries

Additionally, when a single Juju event is triggered, the data flow among the
different layers generally follows the following recognizable pattern:

- Data comes from certain sources (e.g., charm config, integration databag, Juju
  secrets, etc.)
- Data flows to certain sinks (e.g., integration databag, workload configs,
  workload environment variables, etc.)
- Orchestration layer coordinates the data flow from sources to sinks

This allows for a clear separation of concerns and makes the codebase more
maintainable and testable.

### Charm-specific Testing

This charmed operator uses `pytest` for unit and integration tests. Agents *
*MUST** follow these guidelines when contributing tests:

- Name test files starting with `test_` and test functions/methods starting with
  `test_`
- Follow Arrange-Act-Assert (AAA) pattern in test implementations
- Mock external dependencies and interactions using `unittest.mock` or
  `pytest-mock`
- Try to ensure tests are isolated and independent of each other
- Use pytest fixtures for setting up common test scenarios
- Use
  [`ops.testing`](https://documentation.ubuntu.com/ops/latest/reference/ops-testing/)
  for unit tests
- Use [`jubilant`](https://github.com/canonical/jubilant) for integration tests

### Development and Testing Expectations

Before proposing changes, agents **MUST** ensure:

- Code changes are covered by unit or integration tests as appropriate
- Use of `tox` for running formatters, linters, and tests by following the
  commands below:

  ```shell
  tox -e fmt           # format code
  tox -e lint          # lint code
  tox -e unit          # run unit tests
  tox -e integration   # run integration tests
  ```

- All tests pass locally before proposing changes
- Respect the pre-commit hooks defined in `.pre-commit-config.yaml`
- Follow the Conventional Commits specification for commit messages

### What Agents Should Avoid

- Introduce dependencies on external services without human maintainer approval
- Make changes that could introduce security vulnerabilities
- Make changes that could degrade performance without justification
- Make large-scale refactors without explicit human guidance
- Fail to adhere to the coding styles and conventions
- Neglect to follow the established design patterns specific to this charmed
  operator
- Neglect documentation updates when introducing new features or changes
- Fail to consider backward compatibility when modifying public interfaces
- Neglect to run all tests before proposing changes
- Neglect to document changes in `README.md` or `CONTRIBUTING.md` as appropriate
- Ignore pre-commit hooks and code quality checks
- Fail to provide clear explanations and context for proposed changes
- Fail to seek human guidance when unsure about design decisions or
  implementation details
