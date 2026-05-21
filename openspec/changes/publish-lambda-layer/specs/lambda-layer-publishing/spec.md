# Spec: lambda-layer-publishing

## ADDED Requirements

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
- **THEN** for every region in `layer/regions.txt` (excluding lines that are blank or start with `#`), a new layer version is published in that region; the published layer's `CompatibleRuntimes` includes every Python version from 3.10 through 3.14, and `CompatibleArchitectures` lists both `x86_64` and `arm64`

#### Scenario: Public read access granted
- **WHEN** the layer has been published in a region
- **THEN** the workflow invokes `lambda:AddLayerVersionPermission` with `Principal='*'`, `Action='lambda:GetLayerVersion'`, `StatementId='PublicRead'`; any AWS principal in any account can subsequently call `aws lambda get-layer-version --layer-name <ARN>` against the layer version

#### Scenario: One region's failure does not block the rest
- **WHEN** the publish in one region fails (transient API error, opt-in not enabled, etc.)
- **THEN** the matrix is configured `fail-fast: false`; the failed region's job reports failure but other regions' jobs proceed and complete normally

#### Scenario: GovCloud and China regions are NOT included
- **WHEN** `regions.txt` is read
- **THEN** no `us-gov-*` or `cn-*` regions appear (different IAM partition and OIDC audience handling; deferred)

### Requirement: SSM parameter ARN discovery per region

For every successful per-region publish, the workflow SHALL write two SSM Parameter Store parameters in that region recording the layer ARN.

The naming convention is:

- `/cfn-handler/<region>/layer-arn/latest` — overwritten on every release, points to the most recent layer version's ARN
- `/cfn-handler/<region>/layer-arn/v<version>` — written once per release, points to that specific version's ARN

Both parameters are `Standard` tier, `String` type, in the maintainer's AWS account.

#### Scenario: A user looks up the latest layer ARN in their region
- **WHEN** a user runs `aws ssm get-parameter --name /cfn-handler/us-east-1/layer-arn/latest --region us-east-1`
- **THEN** the response is the maintainer's account's most recent `cfn-handler` layer ARN in `us-east-1`

#### Scenario: A user pins to a specific version's ARN
- **WHEN** a user runs `aws ssm get-parameter --name /cfn-handler/us-east-1/layer-arn/v1.1.2 --region us-east-1`
- **THEN** the response is the layer ARN that was published when `cfn-handler 1.1.2` released

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
- `lambda:PublishLayerVersion`, `lambda:GetLayerVersion`, `lambda:AddLayerVersionPermission` on `arn:aws:lambda:*:<account>:layer:cfn-handler*`
- `ssm:PutParameter`, `ssm:GetParameter`, `ssm:LabelParameterVersion` on `arn:aws:ssm:*:<account>:parameter/cfn-handler/*`

The role SHALL NOT have any other permissions; it SHALL NOT be granted broad wildcards like `lambda:*` or `iam:*`.

#### Scenario: Role attempts a permission outside its allowlist
- **WHEN** any process holding the publisher role's credentials attempts e.g. `iam:CreateUser`, `s3:GetObject`, or `lambda:DeleteFunction`
- **THEN** AWS denies the action; only the permissions enumerated above succeed

#### Scenario: Role attempts to publish a layer named differently
- **WHEN** the role attempts `lambda:PublishLayerVersion` with `--layer-name something-else`
- **THEN** AWS denies the action; the resource policy ARN does not match `arn:aws:lambda:*:<account>:layer:cfn-handler*`

### Requirement: Repository layout for layer publishing artifacts

A top-level `layer/` directory SHALL hold every artifact specific to Lambda Layer publishing. The directory SHALL contain at least:

- `layer/README.md` — consumer-facing usage documentation (ARN format, SSM lookup, SAM/CDK snippets)
- `layer/MAINTAINER.md` — publisher operational documentation (deploying the IAM CFN, creating the GitHub environment, opt-in region handling)
- `layer/iam-publisher.cfn.yaml` — CloudFormation template for the OIDC-federated IAM role
- `layer/regions.txt` — newline-delimited region list with `#` comments allowed; sourced directly by the release.yml matrix

#### Scenario: Adding a region to the publish set
- **WHEN** a maintainer wants to add `eu-south-1` to the publish set
- **THEN** they edit `layer/regions.txt` to include `eu-south-1` on its own line; no other repo file needs to change; the release.yml matrix expansion picks up the new region on the next release

#### Scenario: Reading consumer documentation
- **WHEN** a user wants to learn how to use the published layer
- **THEN** they read `layer/README.md` and find the ARN format, SSM parameter names, and a working SAM template snippet

#### Scenario: Setting up the maintainer's AWS account
- **WHEN** a (re-) maintainer wants to set up layer publishing in a new AWS account
- **THEN** they follow `layer/MAINTAINER.md`'s steps in order: deploy the CFN template, create the GitHub environment, save the role ARN as the environment secret; the next release publishes layers automatically
