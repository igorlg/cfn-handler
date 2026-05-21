# Lambda Layer publishing — maintainer setup

This document is for the maintainer (`igorlg`) configuring the AWS account
and GitHub environment that the release pipeline uses to publish the
`cfn-handler` Lambda Layer. **End-users consuming the layer should read
[README.md](README.md) instead.**

## Overview

Every successful release of `cfn-handler` triggers three layer-related
GitHub Actions jobs in `release.yml`:

1. `build-layer-zip` — builds `cfn_handler-<version>-layer.zip` and uploads
   it to the GitHub Release.
2. `publish-layer` — matrix over the regions in [`regions.txt`](regions.txt);
   per region, assumes the IAM role via OIDC, calls `lambda:PublishLayerVersion`,
   grants public read, writes SSM parameters.
3. `aggregate-arns` — gathers the per-region ARNs, uploads
   `layer-arns.json` as a release asset, and edits the GitHub Release body
   to append a per-region ARN markdown table.

Steps 2 and 3 require the IAM role and the GitHub environment configured
below. Without them, the jobs fail at credential acquisition; the rest of
the release pipeline (PyPI publish, etc.) is unaffected.

## One-time AWS account setup

These steps must be completed **before** the first release that includes
the layer-publishing jobs. After that, no further AWS-side action is needed
unless you rotate the role or add regions.

### 1. Deploy the IAM role CloudFormation stack

The CloudFormation template at [`iam-publisher.cfn.yaml`](iam-publisher.cfn.yaml)
creates:

- An OIDC identity provider for GitHub Actions
  (`token.actions.githubusercontent.com`).
- An IAM role named `cfn-handler-layer-publisher` whose trust policy
  permits assumption only by GitHub Actions runs of `igorlg/cfn-handler`
  inside the `layer-publisher` environment.
- Two inline policies scoping the role to `cfn-handler*` named layers and
  `/cfn-handler/*` SSM parameters; nothing else.

```bash
# Pick any commercial region for the stack — the role is global.
aws cloudformation deploy \
  --stack-name cfn-handler-layer-publisher \
  --template-file layer/iam-publisher.cfn.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

If the OIDC provider already exists in your account (from a previous project),
re-run with `--parameter-overrides CreateOidcProvider=false` to skip creating it:

```bash
aws cloudformation deploy \
  --stack-name cfn-handler-layer-publisher \
  --template-file layer/iam-publisher.cfn.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1 \
  --parameter-overrides CreateOidcProvider=false
```

Capture the role ARN from the stack outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name cfn-handler-layer-publisher \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`RoleArn`].OutputValue' \
  --output text
```

The output looks like `arn:aws:iam::<account-id>:role/cfn-handler-layer-publisher`.

### 2. Create the `layer-publisher` GitHub environment

In the GitHub UI for `igorlg/cfn-handler`:

1. Settings → Environments → **New environment** → name it `layer-publisher`.
2. Leave **all** protection rules unchecked. The release pipeline runs from
   release-please bot PRs; required-reviewers / wait-timer rules would block
   bot-driven releases.
3. Save.

### 3. Add the role ARN as a secret

Inside the new `layer-publisher` environment:

1. **Add secret** → name `LAYER_PUBLISHER_ROLE_ARN`, value = the ARN from
   step 1.
2. Save.

The release pipeline references it as `${{ secrets.LAYER_PUBLISHER_ROLE_ARN }}`
inside the `publish-layer` job (which has `environment: layer-publisher`).

### 4. (Optional) Verify the OIDC provider exists

```bash
aws iam list-open-id-connect-providers \
  --query 'OpenIDConnectProviderList[?contains(Arn, `token.actions.githubusercontent.com`)]'
```

Expected: a single ARN matching the canonical GitHub Actions provider.

## Adding a region

The release matrix is generated from [`regions.txt`](regions.txt). To add
a region:

1. Confirm the region is supported by AWS Lambda *and* enabled in your
   account (some regions are opt-in: AWS Console → IAM Identity Center →
   Account → Regions; or `aws account enable-region --region-name <name>`).
2. Add the region to `regions.txt` on a new line (alphabetically sorted to
   keep diffs clean).
3. Open a PR; `secure-workflows.yml` runs against the workflow file, but
   the new region won't actually be used until the PR merges and a release
   triggers.

## Removing a region

Delete the line from `regions.txt`. The release pipeline will stop publishing
new layer versions to that region. **Existing layer versions remain published
in the region** — `aws lambda` doesn't support layer-version deletion via the
default policy. If you want to remove them, add `lambda:DeleteLayerVersion`
to the role's policy temporarily and run a one-off cleanup script.

## Rotating the IAM role

Re-deploying the CloudFormation stack with `aws cloudformation deploy` is
idempotent and updates the role in place. To change the role name (which
forces recreation):

1. Update `RoleName` in `iam-publisher.cfn.yaml` (or pass via
   `--parameter-overrides`).
2. Re-deploy.
3. Update the `LAYER_PUBLISHER_ROLE_ARN` secret in the GitHub environment
   to the new ARN.

## Disabling layer publishing

If you need to pause layer publishing (e.g. during AWS account migration):

- **Quick stop** — delete the GitHub `layer-publisher` environment. The
  `publish-layer` jobs will fail at environment activation; the rest of
  the release pipeline (PyPI publish, GH Release ZIP) continues normally.
- **Full removal** — also delete the CFN stack:
  `aws cloudformation delete-stack --stack-name cfn-handler-layer-publisher --region us-east-1`.

## Troubleshooting

### `publish-layer` fails at "configure-aws-credentials"

Likely causes:
- The `layer-publisher` GitHub environment doesn't exist (create per step 2 above).
- `LAYER_PUBLISHER_ROLE_ARN` secret missing or wrong (check inside the
  `layer-publisher` environment, not at the repository level).
- Trust policy mismatch — re-deploy the CFN stack or inspect the role's
  trust policy in the IAM console; the `sub` condition must match
  `repo:igorlg/cfn-handler:environment:layer-publisher`.

### `lambda:PublishLayerVersion` fails with `AccessDenied` on a specific region

The region is probably opt-in and not enabled in your account. Enable it
(`aws account enable-region --region-name <name>`) and re-run the failed
matrix entry via `gh run rerun --failed`.

### `lambda:AddLayerVersionPermission` fails with `ResourceConflictException`

The `PublicRead` statement was added on a previous run with the same
`StatementId`. Lambda doesn't allow adding a duplicate statement. The
workflow handles this idempotently — it ignores the conflict and continues
because the policy is already in place.

### Region count drift (regions.txt has N, AWS account has M enabled)

`regions.txt` is the source of truth. If a region is in `regions.txt` but
the account hasn't opted into it, that matrix entry fails (transient until
opt-in completes; permanent without it). If a region is enabled in the
account but not in `regions.txt`, no layer is published there — add the
region to `regions.txt`.

## Cost

- IAM role + OIDC provider: free.
- Lambda layers: storage is free; per-region replication is by re-publishing
  (no egress cost).
- SSM Parameter Store, Standard tier: free up to 10,000 parameters; we use
  ~34 per release (17 regions × 2 parameter names).

Total expected monthly cost: $0 unless the publish surface scales 10x.

## See also

- [README.md](README.md) — consumer-facing usage of the published layer.
- [`../docs/CI.md`](../docs/CI.md) — broader CI/release pipeline reference.
- [`../openspec/changes/archive/2026-05-21-publish-lambda-layer/`](../openspec/changes/archive/) — original proposal and design rationale (after this change is archived).
