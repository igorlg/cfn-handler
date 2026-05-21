# cfn-handler

[![CI](https://github.com/igorlg/cfn-handler/actions/workflows/ci.yml/badge.svg)](https://github.com/igorlg/cfn-handler/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cfn-handler.svg)](https://pypi.org/project/cfn-handler/)
[![Python Versions](https://img.shields.io/pypi/pyversions/cfn-handler.svg)](https://pypi.org/project/cfn-handler/)
[![Lambda Layer](https://img.shields.io/github/v/release/igorlg/cfn-handler?label=lambda%20layer&color=ff9900&logo=amazonaws)](https://github.com/igorlg/cfn-handler/releases/latest)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

A modern, well-engineered Python library for writing AWS CloudFormation
**Custom Resource** lifecycle handlers. Inspired by — but not derived from —
the unmaintained [`aws-cloudformation/custom-resource-helper`][upstream].

[upstream]: https://github.com/aws-cloudformation/custom-resource-helper

## Why cfn-handler?

CloudFormation Custom Resources are AWS Lambda functions invoked during stack
operations. Getting them right is harder than it looks: you must respond to a
presigned URL within the Lambda timeout, handle CREATE/UPDATE/DELETE semantics
correctly, manage long-running operations via polling, and never leave
CloudFormation hanging.

`cfn-handler` does the boilerplate so you can focus on the resource logic.

```python
from cfn_handler import CustomResource

resource = CustomResource()

@resource.create
def on_create(event, context):
    # do work, return data dict
    return {"Endpoint": "https://my.example.com"}

@resource.update
def on_update(event, context):
    return {"Endpoint": "https://my.example.com"}

@resource.delete
def on_delete(event, context):
    pass

def handler(event, context):
    return resource(event, context)
```

That's the entire happy path. For long-running operations:

```python
@resource.create
def on_create(event, context):
    # kick off work; return None to defer
    pass

@resource.poll_create
def on_poll_create(event, context):
    # check status; return data when done, raise on failure
    if check_ready():
        return {"Endpoint": "https://my.example.com"}
    # else: do nothing, library will reschedule
```

## Installation

```sh
pip install cfn-handler
# or with uv
uv add cfn-handler
```

`cfn-handler` requires Python 3.10+ and has **zero runtime dependencies**.
Polling support uses `boto3` lazily; `boto3` ships preinstalled in the AWS
Lambda Python runtimes, so no extra install is needed there.

### Or use the AWS Lambda Layer

Every release publishes a public Lambda Layer in ~17 commercial regions. To
use it, reference the ARN in your function definition — no `pip install`
during deploy, no vendoring into your function package:

```yaml
# SAM
Resources:
  MyFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: python3.12
      Layers:
        - arn:aws:lambda:us-east-1:<account-id>:layer:cfn-handler:N
```

Find the right ARN for your region in the [latest release notes][latest-release]
(per-region table) or the JSON manifest:

```sh
curl -fsSL https://github.com/igorlg/cfn-handler/releases/latest/download/layer-arns.json
```

See [`layer/README.md`](layer/README.md) for SAM/CDK snippets, the alternative
deploy-it-yourself path, and the maintainer's account ID.

[latest-release]: https://github.com/igorlg/cfn-handler/releases/latest

## Comparison to crhelper

If you're coming from [`crhelper`][upstream], the model will feel familiar:

| Feature | crhelper | cfn-handler |
|---|---|---|
| Lifecycle decorators | `@helper.create`, `@helper.update`, `@helper.delete` | `@resource.create`, `@resource.update`, `@resource.delete` |
| Polling decorators | `@helper.poll_create` ... | `@resource.poll_create` ... |
| Type hints | None | Full inline (`py.typed`) |
| Python versions | 3.6+ (last release 2020) | 3.10–3.14 |
| Build | `setup.py` | `pyproject.toml` (PEP 621, hatchling) |
| Tests | unittest | pytest + hypothesis |
| Coverage gate | None | 95% line + branch |
| Type checkers | None | mypy strict + pyright strict |
| Releases | Manual | release-please + PyPI Trusted Publishing |
| Maintained | No (since 2020) | Yes |

The public API is intentionally similar — `cfn-handler` is a clean
re-implementation that carries forward the proven semantics and fixes 14
long-standing upstream issues that never merged. See [CHANGELOG.md](CHANGELOG.md)
for the full list.

## Examples

Working SAM-deployable examples live in `examples/`:

- `examples/basic/` — minimal Create/Update/Delete handler.
- `examples/polled/` — long-running operation with polling.
- `examples/with-physical-id/` — explicit physical resource id (replacement on update).
- `examples/failing/` — handler that fails, demonstrating FAILED-response semantics.

## Project status

v1.0.0 — first stable release. Follows [Semantic Versioning](https://semver.org).
The public API surface is exactly what's exported from `cfn_handler.__all__`;
everything under `cfn_handler._internal` is implementation detail and may
change between minor versions.

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for the development workflow,
commit conventions, and lockfile policy. For contributors who use Nix, a
`flake.nix` provides a reproducible dev shell. The CI/release pipeline
itself is documented in [docs/CI.md](docs/CI.md), including the
local-replay tooling and a postmortem of the v1.0.0 release failure.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

This project is inspired by, but does not include code from,
[aws-cloudformation/custom-resource-helper][upstream]. Both projects are
licensed under Apache 2.0.
