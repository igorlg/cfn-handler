# Security policy

## Supported versions

The latest minor version of `cfn-handler` receives security fixes. Older
minor versions may receive fixes at the maintainer's discretion if the
issue is severe and the fix is straightforward.

| Version | Supported |
|---|---|
| 1.x.x   | Yes       |
| < 1.0   | No        |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Use GitHub's private security advisory form:

  https://github.com/igorlg/cfn-handler/security/advisories/new

When reporting, please include:

- A description of the issue and its impact.
- Steps to reproduce, including the affected version of `cfn-handler`.
- Any relevant logs, stack traces, or proof-of-concept code.
- Your assessment of the severity (CVSS score helpful but not required).

You can expect an initial response within 7 days. Coordinated disclosure
timelines are negotiated case-by-case once the issue is triaged.

## What's in scope

- The `cfn_handler` Python package as published on PyPI.
- The CI / release infrastructure in this repository (anything that
  could affect supply chain integrity of published artifacts).

## What's out of scope

- AWS CloudFormation itself, AWS Lambda, or any other AWS service.
- The example code under `examples/` (educational; not published).
- The `aws-cloudformation/custom-resource-helper` upstream project.
