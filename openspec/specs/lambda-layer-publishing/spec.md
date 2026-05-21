# lambda-layer-publishing Specification

## Purpose

Publish a public-read AWS Lambda Layer for the `cfn-handler` Python package on every release: one Layer ZIP attached to the GitHub Release, plus per-region `cfn-handler` layer versions in every commercial AWS region listed in `layer/regions.txt`. Users in any AWS account reference the layer by ARN (no `pip install`, no vendored copy in their function package, smaller deploys); the maintainer's release pipeline (release.yml) drives the entire publish via OIDC-federated IAM (no long-lived AWS credentials in CI). Three public ARN-discovery surfaces let consumers find the right ARN without AWS credentials: the GitHub Release body's per-region table, the `layer-arns.json` release asset, and a shields.io badge in README.md.

## Requirements
### Requirement: Lambda Layer ZIP attached to every GitHub Release

Every successful release SHALL produce a Lambda Layer ZIP artifact named `cfn_handler-<version>-layer.zip` and SHALL upload it to the GitHub Release alongside the wheel and sdist. The ZIP SHALL be a valid Python Lambda Layer: top-level entry `python/`, containing the unpacked wheel contents minus the `*.dist-info/` directory.

#### Scenario: A new release ships
- **WHEN** the release-please PR is squash-merged and `release-please-action` reports `release_created=true`
- **THEN** a `cfn_handler-<version>-layer.zip` artifact appears on the GitHub Release at `https://github.com/igorlg/cfn-handler/releases/tag/v<version>`

#### Scenario: ZIP layout is layer-compatible
- **WHEN** the layer ZIP is unzipped
- **THEN** the unpacked tree begins with `python/cfn_handler/__init__.py`, mirrors the wheel's `cfn_handler/` package contents, and contains no `*.dist-info/` directory

#### Scenario: ZIP contents match the wheel
- **WHEN** the layer ZIP and the wheel from the same release are compared
- **THEN** every file under `python/cfn_handler/` in the ZIP is byte-identical to the corresponding file in the wheel (the layer is the wheel, repackaged for Lambda's filesystem layout)

### Requirement: Per-region Lambda Layer published with public read access

For every region listed in `layer/regions.txt`, every successful release SHALL publish a new Lambda Layer version named `cfn-handler` to that region and SHALL grant public read access via a layer-version resource policy.

#### Scenario: Layer published to all regions in `regions.txt`
- **WHEN** a release is created
- **THEN** for every region in `layer/regions.txt` (excluding lines that are blank or start with `#`), a new layer version is published in that region; the published layer's `CompatibleRuntimes` is derived at release time from the `Programming Language :: Python :: 3.X` classifiers in `pyproject.toml` (so the runtime list is always in sync with the package's declared support), and `CompatibleArchitectures` lists both `x86_64` and `arm64`

#### Scenario: Public read access granted
- **WHEN** the layer has been published in a region
- **THEN** the workflow invokes `lambda:AddLayerVersionPermission` with `Principal='*'`, `Action='lambda:GetLayerVersion'`, `StatementId='PublicRead'`; any AWS principal in any account can subsequently call `aws lambda get-layer-version --layer-name <ARN>` against the layer version

#### Scenario: One region's failure does not block the rest
- **WHEN** the publish in one region fails (transient API error, opt-in not enabled, etc.)
- **THEN** the matrix is configured `fail-fast: false`; the failed region's job reports failure but other regions' jobs proceed and complete normally

#### Scenario: GovCloud and China regions are NOT included
- **WHEN** `regions.txt` is read
- **THEN** no `us-gov-*` or `cn-*` regions appear (different IAM partition and OIDC audience handling; deferred)

### Requirement: Public ARN discovery via GitHub Release surfaces

After every successful release, every per-region ARN published SHALL be discoverable by external users via at least three public surfaces that require no AWS credentials:

1. The GitHub Release body for `v<version>` SHALL contain a per-region ARN markdown table. The table SHALL be appended to the existing release-please-generated notes by an `aggregate-arns` workflow job after all `publish-layer` matrix entries complete (whether successful or failed).
2. A release asset named `layer-arns.json` SHALL be uploaded to the GitHub Release. Its content SHALL be a JSON object with at minimum: `version` (string), `layer_name` (string, currently `cfn-handler`), and `regions` (object mapping each region name to its ARN string). Failed regions SHALL appear with an explanatory `null` value or be omitted.
3. The README SHALL contain a shields.io badge using the GitHub-native release endpoint (`https://img.shields.io/github/v/release/<owner>/<repo>?label=lambda%20layer`). The badge SHALL link to the latest GitHub Release page.

#### Scenario: User browses to the GitHub Release for a version
- **WHEN** a user opens `https://github.com/igorlg/cfn-handler/releases/tag/v<version>` in a browser
- **THEN** the release notes contain a "Lambda Layer ARNs" section with a markdown table listing every region that successfully published, alongside its full ARN

#### Scenario: User fetches the JSON manifest for the latest release
- **WHEN** a user runs `curl -fsSL https://github.com/igorlg/cfn-handler/releases/latest/download/layer-arns.json`
- **THEN** the response is a valid JSON document with `version`, `layer_name`, and `regions` fields populated

#### Scenario: User pins to a specific version's manifest
- **WHEN** a user runs `curl -fsSL https://github.com/igorlg/cfn-handler/releases/download/v<version>/layer-arns.json`
- **THEN** the response is the manifest for that specific version

#### Scenario: README badge reflects the latest published version
- **WHEN** a user views the README on GitHub or PyPI
- **THEN** the "lambda layer" badge displays the latest GitHub release tag (e.g. `v1.2.0`); clicking it lands on the release page where the ARN table is visible

#### Scenario: Aggregate runs even with partial-region failures
- **WHEN** one or more `publish-layer` matrix entries fail
- **THEN** `aggregate-arns` still runs (it has `if: always()`); the GitHub Release body is augmented with the table of regions that DID succeed; failed regions are listed in the notes with their failure mode

### Requirement: OIDC-federated IAM role for the publisher

The release pipeline's per-region publish jobs SHALL acquire AWS credentials via OIDC federation from GitHub Actions, NOT via stored long-lived AWS access keys. The trust policy of the assumed role SHALL restrict assumption to GitHub Actions runs originating from the `igorlg/cfn-handler` repository AND the `layer-publisher` environment.

#### Scenario: Workflow assumes the role
- **WHEN** the `publish-layer` job runs and invokes `aws-actions/configure-aws-credentials` with `role-to-assume: ${{ secrets.LAYER_PUBLISHER_ROLE_ARN }}` while the workflow's `environment:` is `layer-publisher`
- **THEN** AWS STS issues credentials based on the federated OIDC token; the credentials are scoped to the role's permissions

#### Scenario: A different repo or environment cannot assume the role
- **WHEN** any GitHub Actions workflow that is NOT inside `igorlg/cfn-handler` AND running in the `layer-publisher` environment attempts to assume the role
- **THEN** STS rejects the assumption (`AccessDenied`) because the trust policy's `sub` condition does not match

### Requirement: Publisher-role permissions are least-privilege

The IAM role's permissions SHALL be scoped to:
- `lambda:PublishLayerVersion`, `lambda:GetLayerVersion`, `lambda:GetLayerVersionPolicy`, `lambda:AddLayerVersionPermission`, `lambda:RemoveLayerVersionPermission`, `lambda:ListLayerVersions` on `arn:aws:lambda:*:<account>:layer:cfn-handler` and `arn:aws:lambda:*:<account>:layer:cfn-handler:*`

The role SHALL NOT have any other permissions; it SHALL NOT be granted broad wildcards like `lambda:*` or `iam:*`. It SHALL NOT have any non-Lambda service permissions (no SSM, no S3, no CloudWatch, etc.).

#### Scenario: Role attempts a permission outside its allowlist
- **WHEN** any process holding the publisher role's credentials attempts e.g. `iam:CreateUser`, `s3:GetObject`, or `lambda:DeleteFunction`
- **THEN** AWS denies the action; only the permissions enumerated above succeed

#### Scenario: Role attempts to publish a layer named differently
- **WHEN** the role attempts `lambda:PublishLayerVersion` with `--layer-name something-else`
- **THEN** AWS denies the action; the resource policy ARN does not match `arn:aws:lambda:*:<account>:layer:cfn-handler*`

### Requirement: Repository layout for layer publishing artifacts

A top-level `layer/` directory SHALL hold every artifact specific to Lambda Layer publishing. The directory SHALL contain at least:

- `layer/README.md` — consumer-facing usage documentation (ARN format, SAM/CDK snippets)
- `layer/MAINTAINER.md` — publisher operational documentation (deploying the IAM CFN, creating the GitHub environment, opt-in region handling)
- `layer/iam-publisher.cfn.yaml` — CloudFormation template for the OIDC-federated IAM role
- `layer/regions.txt` — newline-delimited region list with `#` comments allowed; sourced directly by the release.yml matrix

#### Scenario: Adding a region to the publish set
- **WHEN** a maintainer wants to add `eu-south-1` to the publish set
- **THEN** they edit `layer/regions.txt` to include `eu-south-1` on its own line; no other repo file needs to change; the release.yml matrix expansion picks up the new region on the next release

#### Scenario: Reading consumer documentation
- **WHEN** a user wants to learn how to use the published layer
- **THEN** they read `layer/README.md` and find the ARN format and a working SAM template snippet

#### Scenario: Setting up the maintainer's AWS account
- **WHEN** a (re-) maintainer wants to set up layer publishing in a new AWS account
- **THEN** they follow `layer/MAINTAINER.md`'s steps in order: deploy the CFN template, create the GitHub environment, save the role ARN as the environment secret; the next release publishes layers automatically

