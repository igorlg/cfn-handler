# Design: Publish a Lambda Layer

## Context

Lambda Layers are a deploy-time mechanism for shipping shared code to Lambda functions. AWS hosts the layer; consumers reference it by ARN; the layer's contents are mounted at `/opt/<runtime>/` at function-invocation time.

For pure-Python libraries, the conventional packaging is:

```
<layer-zip>
└── python/
    └── cfn_handler/
        ├── __init__.py
        ├── exceptions.py
        ├── resource.py
        ├── py.typed
        └── _internal/
            └── ...
```

`/opt/python/` is on the Python path at invocation; `from cfn_handler import CustomResource` works without any further config.

A layer is published in one specific AWS region. To make the layer available globally, the maintainer publishes it independently in each region and gives each layer version's resource policy a public-read grant. Consumers reference the region-local ARN.

The reference implementation in this ecosystem is `aws-powertools/powertools-lambda-python`, which publishes per-region layers with public read across ~30 commercial regions, plus separate pipelines for GovCloud and China partitions. We're not matching that scale — see Non-goals — but the architecture is the same.

## Goals / Non-Goals

**Goals:**

- Layer ZIP attached to every GitHub Release (cheap, available even if cross-region publishing fails).
- Public-read Layer ARNs in every commercial region the maintainer has enabled.
- ARN discovery via three public surfaces — augmented GitHub Release body, `layer-arns.json` release asset, and README shields.io badge — none of which require AWS credentials.
- One ZIP works for all supported Python versions (3.10–3.14) and architectures (x86_64, arm64) — pure Python, zero deps.
- OIDC-federated IAM role; no long-lived AWS credentials in GitHub secrets.
- `layer/regions.txt` is the single source of truth for which regions get published; release.yml's matrix is generated from it.
- `pyproject.toml`'s `Programming Language :: Python :: 3.X` classifiers are the single source of truth for `--compatible-runtimes`; release.yml derives the runtime list at publish time so the layer's declared support cannot drift from the package's.
- Failure in one region doesn't block other regions (`fail-fast: false` matrix).

**Non-Goals:**

- GovCloud (`us-gov-*`), China (`cn-*`), or SAR app publishing.
- Canary stack post-publish.
- SLSA provenance on the layer ZIP (out of scope; wheel already covers supply-chain attestation).
- Auto-opt-in to regions like `ap-east-1`, `me-south-1`, `af-south-1`. These need account-level opt-in; the `regions.txt` file lists explicitly-supported regions only.
- A Layer Construct library (CDK helper) — defer until users actually ask.

## Decisions

### D1 — Layer ZIP structure: one universal ZIP per release

Pure-Python zero-deps means the ZIP is identical regardless of target Python version or architecture. We ship one `cfn_handler-X.Y.Z-layer.zip` whose top-level dir is `python/`, containing the unpacked wheel contents minus the `dist-info` metadata (the `dist-info` is for pip's bookkeeping; not needed at runtime). The published layer's `CompatibleRuntimes` is derived from `pyproject.toml`'s `Programming Language :: Python :: 3.X` classifiers (so the runtime list can never drift from the package's declared support); `CompatibleArchitectures` lists both `x86_64` and `arm64`. AWS validates these at function-association time but the actual content works on all combinations.

Considered: per-Python-version layers (5 ZIPs per release). Powertools does this; reasoning is they have C extensions for some optional features. We don't have C extensions and never will (zero-dep policy). One ZIP is simpler and correct.

### D2 — Region scope: `regions.txt` + non-opt-in regions only at first

The list of regions the layer publishes to lives in `layer/regions.txt`, one per line, with `#` comments allowed. The release.yml matrix reads this file directly via `jq` or shell. Adding/removing a region is a one-line PR.

Initial list is the ~17 commercial regions enabled by default in any AWS account (no opt-in required):

```
us-east-1
us-east-2
us-west-1
us-west-2
eu-west-1
eu-west-2
eu-west-3
eu-central-1
eu-north-1
ap-northeast-1
ap-northeast-2
ap-northeast-3
ap-southeast-1
ap-southeast-2
ap-south-1
ca-central-1
sa-east-1
```

The proposal mentions ~30 regions; the gap is opt-in regions (`ap-east-1`, `af-south-1`, `eu-south-1`, `eu-south-2`, `eu-central-2`, `me-south-1`, `me-central-1`, `il-central-1`, `ap-southeast-3`, `ap-southeast-4`, `ap-south-2`, `ap-northeast-3`, etc.). These need account-level opt-in *and* AWS Lambda regional support. The maintainer can enable them in the AWS account and add to `regions.txt` as a follow-up.

### D3 — IAM role: OIDC-federated, environment-scoped

The IAM role lives in the maintainer's AWS account. Trust policy:

```json
{
  "Effect": "Allow",
  "Principal": { "Federated": "arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com" },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
    },
    "StringLike": {
      "token.actions.githubusercontent.com:sub": "repo:igorlg/cfn-handler:environment:layer-publisher"
    }
  }
}
```

The `sub` condition restricts assumption to GitHub Actions runs inside the `layer-publisher` environment of `igorlg/cfn-handler`. Branch protection enforces that environment-scoped jobs only run after `release-please` succeeds in `release.yml` — there's no other path for an attacker (with write access to the repo) to abuse the role.

Permissions:

```json
{
  "Effect": "Allow",
  "Action": [
    "lambda:PublishLayerVersion",
    "lambda:GetLayerVersion",
    "lambda:GetLayerVersionPolicy",
    "lambda:AddLayerVersionPermission",
    "lambda:RemoveLayerVersionPermission",
    "lambda:ListLayerVersions"
  ],
  "Resource": [
    "arn:aws:lambda:*:<account>:layer:cfn-handler",
    "arn:aws:lambda:*:<account>:layer:cfn-handler:*"
  ]
}
```

Resource scoping ensures the role can only touch `cfn-handler*` named layers; no escape hatch into the broader account, no permissions to non-Lambda services. CloudFormation template `layer/iam-publisher.cfn.yaml` codifies this.

### D4 — Public read access via `lambda:AddLayerVersionPermission`

After each `PublishLayerVersion`, the workflow invokes:

```
aws lambda add-layer-version-permission \
  --layer-name cfn-handler \
  --version-number <N> \
  --statement-id PublicRead \
  --action lambda:GetLayerVersion \
  --principal '*'
```

This adds a resource policy granting any AWS principal `lambda:GetLayerVersion`. Without it, only the maintainer's account could reference the layer; anyone else gets `AccessDenied`.

`StatementId: PublicRead` is the same identifier on every layer version (no need to vary; the resource policy is per-version). If the policy fails to apply, the workflow continues — the ARN is still valid for the maintainer's testing, just not for public consumption. A separate verification step asserts the public read grant.

### D5 — Layer name: `cfn-handler`

Same name as the PyPI package. Discoverable. Considered alternatives:

- `cfn-handler-python` — disambiguates from a hypothetical TS layer. Rejected because we don't have a polyglot story; YAGNI.
- `cfn-handler-py3` — version-prefix. Rejected because the runtime version is part of `CompatibleRuntimes`; redundant.
- `igorlg-cfn-handler` — namespaces the layer by maintainer. Rejected because layer ARNs already include the account ID; the layer NAME doesn't need to.

### D6 — Failure semantics: per-region failures are isolated

Matrix uses `fail-fast: false`. A single bad region (e.g. transient AWS API hiccup, account opt-in lapse) reports failure but doesn't cancel the other matrix entries. Successful regions get their layer published; failed regions can be retried via `workflow_dispatch` on `release.yml` (which already exists for manual re-trigger).

The release-pipeline as a whole reports green if `release-please` succeeded and the wheel/sdist published to PyPI even if a few region publishes failed — those are *additional* surfaces, not the canonical artifact.

### D7 — Build the layer ZIP from the wheel

The build job extracts `dist/*.whl` into `build/python/`, strips the `*.dist-info` metadata (not needed at runtime), and zips the result. This guarantees layer contents match the published wheel's contents exactly (same bytes, same `__version__`, same py.typed marker).

```bash
mkdir -p build/python
unzip -q dist/cfn_handler-*.whl -d build/python
rm -rf build/python/*.dist-info
( cd build && zip -qr "../dist/cfn_handler-${VERSION}-layer.zip" python/ )
```

Considered: building the layer from source directly (`pip install -t build/python/ -e .`). Rejected because the wheel is already the canonical built artifact; rebuilding from source risks divergence.

### D8 — One-time maintainer setup is documented in `layer/MAINTAINER.md`

The CFN template, the GitHub environment, and the secret all need to be created before the release pipeline can publish. `layer/MAINTAINER.md` walks through:

1. Open the AWS account; deploy `layer/iam-publisher.cfn.yaml`:
   ```bash
   aws cloudformation deploy --stack-name cfn-handler-layer-publisher \
     --template-file layer/iam-publisher.cfn.yaml \
     --capabilities CAPABILITY_NAMED_IAM
   ```
2. Output is the role ARN.
3. In GitHub: Settings → Environments → New environment → `layer-publisher`. Add secret `LAYER_PUBLISHER_ROLE_ARN` = the ARN from step 2.
4. Push a `feat:` or `fix:` commit; release-please opens the next release PR; merge it; observe the per-region publish jobs.

Idempotent: re-deploying the CFN template is a no-op; rotating the role ARN is one CFN update.

### D9 — User-facing ARN discovery (three public surfaces)

Three public surfaces let users discover ARNs without AWS credentials or cross-account trust:

**1. GitHub Release body augmentation (primary).** The `aggregate-arns` job, after all per-region publishes complete, edits the GitHub Release notes via `gh release edit --notes-file -` to append a per-region ARN markdown table:

```markdown
## Lambda Layer ARNs

| Region | ARN |
|---|---|
| us-east-1 | `arn:aws:lambda:us-east-1:<account>:layer:cfn-handler:<n>` |
| us-east-2 | `arn:aws:lambda:us-east-2:<account>:layer:cfn-handler:<n>` |
| ... |
```

Anyone landing on `https://github.com/igorlg/cfn-handler/releases/tag/v<version>` sees ARNs at a glance.

**2. `layer-arns.json` release asset (programmatic).** Same job uploads a structured manifest:

```json
{
  "version": "1.2.0",
  "layer_name": "cfn-handler",
  "regions": {
    "us-east-1": "arn:aws:lambda:us-east-1:<account>:layer:cfn-handler:N",
    "us-east-2": "arn:aws:lambda:us-east-2:<account>:layer:cfn-handler:N",
    ...
  }
}
```

Fetch via `curl -L https://github.com/igorlg/cfn-handler/releases/latest/download/layer-arns.json` for "always latest" or pin a specific version with `…/releases/download/v1.2.0/layer-arns.json`.

**3. shields.io badge (visual signal).** README adds:

```markdown
[![Lambda Layer](https://img.shields.io/github/v/release/igorlg/cfn-handler?label=lambda%20layer&color=ff9900&logo=amazonaws)](https://github.com/igorlg/cfn-handler/releases/latest)
```

Uses the GitHub-native release endpoint (no custom server, no extra infrastructure). Updates automatically on every release. Color matches AWS orange. Click-through goes to the latest release page where the ARN table lives.

Considered: a committed `layer/arns.json` file updated via automated PR after each release. Rejected — adds a workflow that opens a PR per release; brittle. The release-asset approach delivers the same JSON without the PR ceremony.

Considered: a region-count badge (`shields.io/badge/regions-17-blue`). Rejected — low signal; users care about whether their region is covered, not the count. The README's "Lambda Layer" section names the regions explicitly.

### Aggregate-arns job mechanics

Per-region `publish-layer` jobs each upload a small artifact (`arn-<region>.json` containing `{"region": "...", "arn": "..."}`) via `actions/upload-artifact`. The `aggregate-arns` job depends on `publish-layer` (so it runs after the matrix completes), uses `actions/download-artifact` to gather every per-region artifact, builds the consolidated `layer-arns.json`, generates the markdown table, then:

```bash
gh release upload v$VERSION layer-arns.json --clobber
gh release edit v$VERSION --notes "$(cat existing-notes)\n\n## Lambda Layer ARNs\n\n$(cat arns-table.md)"
```

`if: always()` on the aggregate job so partial-region success still produces an inventory of what DID publish.

## Risks / Trade-offs

- **[Risk] AWS API rate limits at scale.** ~17 regions × (`PublishLayerVersion` + `AddLayerVersionPermission`) = ~34 API calls per release. Lambda's `PublishLayerVersion` rate limit is ~10/sec/account, well above this; not a concern at our scale. Documented as a known watch-item if region count grows past 30.
- **[Risk] Layer accumulation.** Each release creates a new layer version in every region. AWS keeps all versions; storage is free but versions accumulate. After 100 releases × 17 regions = 1700 layer versions in the account. No deletion policy applied (Powertools doesn't either). Mitigation: spec a `prune-old-layer-versions` workflow as a future change if it becomes painful.
- **[Risk] Maintainer absence.** If the maintainer's AWS account is suspended or the role is deleted, layer publishing fails forever; PyPI publishing continues (different mechanism). Documented in `layer/MAINTAINER.md`; user-facing impact is "users pin to the wheel via pip" which always works.
- **[Trade-off] Public read access.** Anyone in the world can reference `arn:aws:lambda:<region>:<account>:layer:cfn-handler:N` without any IAM trust on their side. This is a *feature* (the whole point); the risk is that AWS could deprecate the public-grant pattern (no signs of this). Powertools is in the same boat; if AWS changed the model both projects would adapt together.
- **[Trade-off] Layer ZIP shipped via GH Release AND published to AWS.** Two distribution paths, two places to keep in sync. Minor doubling of effort; offset by the GH Release ZIP being a fallback if the AWS publish ever breaks.
- **[Trade-off] One layer name across all regions, all versions.** No way to "yank" a bad version (Lambda doesn't support layer-version yanking). Mitigation: if a release ships broken, ship a fixed release immediately; users updating to the new ARN get the fix.

## Migration Plan

This is additive. No existing artifact changes shape; users continue installing via `pip install cfn-handler` and get exactly what they got before. The layer is a new option alongside, not a replacement.

Order of operations within the implementing PR:

1. Add `layer/` directory with all files (`README.md`, `MAINTAINER.md`, `iam-publisher.cfn.yaml`, `regions.txt`).
2. Add `build-layer-zip` and `publish-layer` jobs to `.github/workflows/release.yml` behind `if: release_created == 'true'` and gated by the new `layer-publisher` environment.
3. Update `docs/CI.md` and `README.md` cross-links.
4. **Maintainer one-time setup** (manually, before merging the PR — see `layer/MAINTAINER.md`):
   - Deploy `iam-publisher.cfn.yaml` to AWS account.
   - Create `layer-publisher` GitHub environment.
   - Add `LAYER_PUBLISHER_ROLE_ARN` secret to that environment.
5. Merge the PR. The next release-please merge triggers the new jobs alongside the existing wheel/sdist publish.

Rollback: if the layer publish itself starts failing, the rest of the release pipeline (PyPI publish, GH Release) is unaffected. The `layer-publisher` environment can be deleted, killing the OIDC trust; the release.yml jobs would fail at credential-acquisition and the remaining release continues normally. Or revert the workflow YAML edits via `git revert`.

## Open Questions

None. Region list is editable; IAM role can be redeployed; layer name is locked in once first published but matches PyPI for clarity.
