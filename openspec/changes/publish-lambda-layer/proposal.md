# Proposal: Publish a Lambda Layer

## Why

Users of `cfn-handler` write AWS Lambda functions that import the library. Today they install it via `pip install cfn-handler` baked into their function package (vendored), or via SAM/CDK build hooks that install it during deploy. Both work but add complexity to the user's deploy pipeline and inflate the function package size by ~20 KB on every function.

A published Lambda Layer is the idiomatic alternative: the maintainer publishes one `cfn-handler` layer per release with public read access; users reference an ARN in their function definition, and the library is mounted at `/opt/python/` at runtime. No vendoring, no build hooks, smaller deploy packages.

`aws-lambda-powertools-python-layer` is the reference implementation in this ecosystem, and most AWS Python Lambda libraries either ship layers or get asked to. We have an AWS account ready and an OIDC trust setup that GitHub Actions can use to deploy across all commercial regions.

## What Changes

### Distribution (user-facing)

- **NEW** Lambda Layer ZIP (`cfn_handler-X.Y.Z-layer.zip`) attached to every GitHub Release alongside the wheel and sdist. Pure-Python, zero-dep, layout-compatible with all supported Python versions and architectures.
- **NEW** Public read-access Lambda Layer published to ~30 commercial AWS regions on every release, named `cfn-handler`. Users reference `arn:aws:lambda:<region>:<igorlg-account-id>:layer:cfn-handler:<version>`.
- **NEW** Per-region SSM parameters under `/cfn-handler/<region>/`:
  - `/cfn-handler/<region>/layer-arn/latest` — pointer to the most recent ARN; users wanting "always latest" reference this.
  - `/cfn-handler/<region>/layer-arn/<version>` — pointer to a specific version's ARN; users wanting reproducibility pin to this.

### Repository (maintainer-facing)

- **NEW** `layer/` top-level directory holding all Lambda Layer publishing artifacts:
  - `layer/README.md` — consumer-facing: ARN format, SSM lookup, SAM/CDK snippets.
  - `layer/MAINTAINER.md` — publisher setup: deploying the IAM role, opt-in region handling, what the release pipeline does.
  - `layer/iam-publisher.cfn.yaml` — CloudFormation template that creates the OIDC-federated IAM role used by GitHub Actions, scoped to the `layer-publisher` environment of this repo.
  - `layer/regions.txt` — canonical list of regions the Layer is published to. One region per line, sorted, comments allowed. Sourced directly by the release.yml matrix.
- **MODIFIED** `.github/workflows/release.yml`:
  - New job `build-layer-zip` runs after `release-please` succeeds. Builds the layer ZIP and uploads it to the GitHub Release.
  - New job `publish-layer` runs after `build-layer-zip`. Per-region matrix: assume role via OIDC → publish layer version → grant public read → write SSM parameters. `fail-fast: false` so a single bad region doesn't block the others.
- **NEW** GitHub repository environment `layer-publisher` (created via UI / API as part of the rollout). Holds the `LAYER_PUBLISHER_ROLE_ARN` secret. Bound by the OIDC trust policy.

### Documentation

- **MODIFIED** `docs/CI.md` — Workflow inventory adds the new layer jobs; brief paragraph in the Release pipeline section pointing readers at `layer/README.md` for layer-specific operational detail.
- **MODIFIED** `README.md` — short section under "Installation" introducing the layer option alongside `pip install`.

### Non-goals

- **No** GovCloud (`us-gov-east-1`, `us-gov-west-1`) regions in this iteration. Adds different IAM partition handling and a separate AWS account; deferred to a future change if needed.
- **No** China (`cn-north-1`, `cn-northwest-1`) regions. Different OIDC audience, different account model, deferred.
- **No** SAR app publishing. SAR is a third path users could consume the library through; we already have ZIP and ARN; deferring.
- **No** SLSA L3 provenance attestation on the layer ZIP. The wheel/sdist already publish via PyPI Trusted Publishing OIDC which is the strong supply-chain signal; layer ZIP integrity matches the wheel content (the layer IS the wheel, repackaged).
- **No** canary stack that deploys the layer to a test Lambda after publish. Future addition if releases ever break.
- **No** automatic opt-in for regions like `ap-east-1`, `me-south-1`, `af-south-1` etc. The `regions.txt` file lists explicitly enabled regions; opt-in regions need to be enabled in the AWS account first, then added to `regions.txt`.

## Capabilities

### New Capabilities

- `lambda-layer-publishing`: per-release Lambda Layer build + publish across commercial regions, with public read access and SSM-parameter ARN discovery.

### Modified Capabilities

None. The `ci-infrastructure` capability covers the test/lint/PyPI-publish pipeline; the layer publish jobs in `release.yml` are a parallel post-release surface that doesn't replace or reshape what's already specified there.

## Impact

- **AWS account**: `igorlg`'s dedicated AWS account holds the layer + SSM parameters. Cost ≈ $0/month (Lambda layers are free in storage; SSM Standard Parameter Store is free up to 10,000 parameters).
- **IAM**: one OIDC-federated role assumed by GitHub Actions only when the `layer-publisher` environment is active in `release.yml`. Trust policy scoped to repo + environment. Permissions scoped to `lambda:*LayerVersion*` on `arn:aws:lambda:*:<account>:layer:cfn-handler*` and `ssm:*Parameter*` under `/cfn-handler/*`.
- **Release time**: ~30 region deploys add ~2-5 minutes wall-clock (parallel matrix; each region's publish is ~5-10 seconds).
- **User-facing**: layer ARNs become available on PyPI release notes / GitHub Release / SSM. No backward compatibility concern (it's a new product surface, not a change to the existing wheel).
- **Setup work for maintainer (Igor)**: one-time before this change can ship — deploy `layer/iam-publisher.cfn.yaml` to your AWS account, create the `layer-publisher` GitHub environment, save the role ARN to the environment secret. All documented in `layer/MAINTAINER.md`.
