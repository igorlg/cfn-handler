# Tasks: Publish a Lambda Layer

## 1. layer/ directory scaffolding

- [x] 1.1 Create `layer/` top-level directory.
- [x] 1.2 Create `layer/regions.txt` with the 17 default-enabled commercial regions, one per line, sorted alphabetically. Document the `#` comment convention with a header comment in the file.
- [x] 1.3 Create `layer/iam-publisher.cfn.yaml` — a CloudFormation template defining: a `AWS::IAM::OIDCProvider` (idempotent — uses existing if already deployed); a `AWS::IAM::Role` named `cfn-handler-layer-publisher` with trust policy scoped to `repo:igorlg/cfn-handler:environment:layer-publisher`; an inline policy granting only `lambda:*LayerVersion*` on `arn:aws:lambda:*:${AWS::AccountId}:layer:cfn-handler*` and `ssm:*Parameter*` on `arn:aws:ssm:*:${AWS::AccountId}:parameter/cfn-handler/*`. Output: the role ARN.
- [x] 1.4 Create `layer/MAINTAINER.md` documenting: how to deploy the CFN template (`aws cloudformation deploy --capabilities CAPABILITY_NAMED_IAM`); how to create the `layer-publisher` GitHub environment; how to add the `LAYER_PUBLISHER_ROLE_ARN` secret; how to add a new region (edit `regions.txt`); how to handle opt-in regions (enable the region in the AWS account first, then add to `regions.txt`); how to roll back by deleting the GitHub environment.
- [x] 1.5 Create `layer/README.md` documenting: the ARN format (`arn:aws:lambda:<region>:<account-id>:layer:cfn-handler:<version>`); how to look up the latest ARN via SSM (`aws ssm get-parameter --name /cfn-handler/<region>/layer-arn/latest`); a SAM template snippet showing how to attach the layer to a function; a CDK snippet (TypeScript or Python); a note that the ZIP is also attached to every GitHub Release for users who'd rather deploy it in their own account.

## 2. Workflow YAML changes

- [x] 2.1 Edit `.github/workflows/release.yml`: add a new job `build-layer-zip` after `release-please`, gated on `release_created == 'true'`. Steps: checkout at the released tag, install uv, build the wheel, extract into `build/python/`, strip `*.dist-info/`, zip as `dist/cfn_handler-${VERSION}-layer.zip`, upload the ZIP to the GitHub Release via `gh release upload`. Job permission: `contents: write` (for `gh release upload`).
- [x] 2.2 Edit `.github/workflows/release.yml`: add a new job `publish-layer`, `needs: [release-please, build-layer-zip]`, gated on `release_created == 'true'`. Set `environment: layer-publisher`. Set `permissions: { id-token: write, contents: read }`. Use `strategy.matrix.region` populated from `layer/regions.txt` via a tiny shell expansion in a preceding `set-matrix` job (or inline in the matrix definition using `fromJSON`).
- [x] 2.3 In `publish-layer`: download the layer ZIP from the GitHub Release; assume the role via `aws-actions/configure-aws-credentials@<sha>` with `role-to-assume: ${{ secrets.LAYER_PUBLISHER_ROLE_ARN }}` and `aws-region: ${{ matrix.region }}`; invoke `aws lambda publish-layer-version` with `--layer-name cfn-handler --license-info Apache-2.0 --description 'cfn-handler ${VERSION}' --zip-file fileb://cfn_handler-${VERSION}-layer.zip --compatible-runtimes python3.10 python3.11 python3.12 python3.13 python3.14 --compatible-architectures x86_64 arm64`; capture the resulting `LayerVersionArn`.
- [x] 2.4 In `publish-layer`: invoke `aws lambda add-layer-version-permission --layer-name cfn-handler --version-number <N> --statement-id PublicRead --action lambda:GetLayerVersion --principal '*'`. Verify the policy was applied via `aws lambda get-layer-version-policy`.
- [x] 2.5 In `publish-layer`: invoke `aws ssm put-parameter --name /cfn-handler/${{ matrix.region }}/layer-arn/latest --value <ARN> --type String --overwrite` and `aws ssm put-parameter --name /cfn-handler/${{ matrix.region }}/layer-arn/v${VERSION} --value <ARN> --type String` (no overwrite for version-specific; idempotent on repeated runs only if the ARN matches).
- [x] 2.6 In `publish-layer`: write `arn-${{ matrix.region }}.json` containing `{"region": "${{ matrix.region }}", "arn": "<ARN>"}` and upload it via `actions/upload-artifact@<sha>` with `name: layer-arns-${{ matrix.region }}` for the aggregate step to consume.
- [x] 2.7 Set `strategy.fail-fast: false` on the `publish-layer` matrix so a single bad region does not cancel the rest.
- [x] 2.8 Add a new job `aggregate-arns`, `needs: [release-please, publish-layer]`, gated on `release_created == 'true'`, with `if: always()` so partial-region success still produces an inventory. `permissions: contents: write`. Steps: download all `layer-arns-*` artifacts via `actions/download-artifact`; read each region's JSON; build a consolidated `layer-arns.json` (`{ "version": "${VERSION}", "layer_name": "cfn-handler", "regions": { "us-east-1": "<ARN>", ... } }`); build a markdown table `arns-table.md` (regions sorted alphabetically; failed regions noted explicitly); upload `layer-arns.json` as a release asset via `gh release upload v${VERSION} layer-arns.json --clobber`; append the markdown table to the release notes via `gh release view v${VERSION} --json body | jq -r .body > existing-notes.md && printf '\n\n## Lambda Layer ARNs\n\n' >> existing-notes.md && cat arns-table.md >> existing-notes.md && gh release edit v${VERSION} --notes-file existing-notes.md`.
- [x] 2.9 SHA-pin every action used in the new jobs (`aws-actions/configure-aws-credentials`, `actions/upload-artifact`, `actions/download-artifact`) with `# vX.Y.Z` comments. `secure-workflows.yml` will re-validate on the PR.

## 3. Docs

- [x] 3.1 Update `docs/CI.md` "Workflow inventory" section: `release.yml` row's "Jobs" column gains `build-layer-zip`, `publish-layer (matrix over regions)`, and `aggregate-arns`.
- [x] 3.2 Update `docs/CI.md` "Release pipeline" section: add a brief paragraph describing the layer publish as a parallel post-release surface alongside PyPI publish; explain the three public ARN discovery surfaces (release body table, `layer-arns.json` asset, shields badge); link to `layer/README.md` for usage and `layer/MAINTAINER.md` for operational detail.
- [x] 3.3 Update `README.md` "Installation" section: add a short paragraph introducing the layer option as an alternative to `pip install`; link to `layer/README.md`. Add a shields.io badge for the current Layer version (`https://img.shields.io/github/v/release/igorlg/cfn-handler?label=lambda%20layer&color=ff9900&logo=amazonaws`) inline with the existing PyPI / Python / License badges, linking to the latest GitHub Release page.

## 4. Local verification (before push)

- [x] 4.1 `just ci-check` — pure tests, no library code change; sanity check.
- [x] 4.2 `act pull_request -W .github/workflows/release.yml --job build-layer-zip --secret GITHUB_TOKEN="$(gh auth token)"`. Note: `act` cannot replicate the AWS OIDC step, so this exercises only the build, not the publish.
- [x] 4.3 Inspect the layer ZIP locally: `uv build && mkdir -p /tmp/layer-build/python && unzip -q dist/*.whl -d /tmp/layer-build/python && rm -rf /tmp/layer-build/python/*.dist-info && ( cd /tmp/layer-build && zip -qr /tmp/cfn-handler-layer.zip python/ ) && unzip -l /tmp/cfn-handler-layer.zip | head -10`. Confirm: top-level `python/`, `python/cfn_handler/__init__.py`, no `dist-info`.

## 5. PR open

- [x] 5.1 Stage all changes; commit with title `feat(layer): publish Lambda Layer to GitHub Releases and all commercial regions`. Note: the `feat:` prefix is correct here — this is a user-facing capability (a new distribution channel).
- [x] 5.2 Branch `feat/lambda-layer-publishing` (already created); push.
- [x] 5.3 `gh pr create` against `main`. PR description: link to `openspec/changes/publish-lambda-layer/proposal.md` and to `layer/MAINTAINER.md`. Highlight the maintainer setup steps Igor must do BEFORE merging.

## 6. Maintainer one-time setup (manual; gates the merge)

- [x] 6.1 Igor: `aws cloudformation deploy --stack-name cfn-handler-layer-publisher --template-file layer/iam-publisher.cfn.yaml --capabilities CAPABILITY_NAMED_IAM --region us-east-1` (the role itself is global; pick any region for the stack). Capture the role ARN from `aws cloudformation describe-stacks --stack-name cfn-handler-layer-publisher --query 'Stacks[0].Outputs'`.
- [x] 6.2 Igor: in the GitHub UI for `igorlg/cfn-handler`, Settings → Environments → New environment → name `layer-publisher`. No protection rules (PR-only releases gate it; protection rules would block release-please's bot).
- [x] 6.3 Igor: in the `layer-publisher` environment, add a secret named `LAYER_PUBLISHER_ROLE_ARN` with the ARN value from 6.1.
- [x] 6.4 Igor: confirm the OIDC provider exists in the AWS account: `aws iam list-open-id-connect-providers`. If the CFN deployed it (first-time setup), it's there. If a previous OIDC provider already existed, the CFN template imports it cleanly.

## 7. Cloud CI on the PR

- [x] 7.1 Watch `secure-workflows.yml` re-validate the new SHAs and report SUCCESS.
- [x] 7.2 Watch `ci.yml` matrix + lint pass (no library changes; should be green).
- [x] 7.3 The new `build-layer-zip` and `publish-layer` jobs do NOT run on PRs — they're gated on `release_created == 'true'`, which only happens after release-please's PR merges. Document this in the PR description so reviewers don't expect to see them.

## 8. Merge + first release

- [ ] 8.1 Squash-merge the PR. Title format: `feat(layer): publish Lambda Layer ...`. The `feat:` triggers a minor bump in the next release-please PR.
- [ ] 8.2 Merge the resulting release-please PR. Watch `release.yml` end-to-end:
   - `release-please` ✓
   - `publish-artifacts` ✓ (existing wheel/sdist + new layer ZIP attached to GH Release)
   - `publish-pypi` ✓ (existing PyPI publish)
   - `build-layer-zip` ✓ (new)
   - `publish-layer` × 17 regions, all ✓ (new; `fail-fast: false` so partial failure is tolerated)
   - `aggregate-arns` ✓ (new; runs `if: always()`; uploads `layer-arns.json` and edits release body)
- [ ] 8.3 Verify a published layer: `aws lambda get-layer-version --layer-name cfn-handler --version-number 1 --region us-east-1` returns the layer; `aws lambda get-layer-version-policy --layer-name cfn-handler --version-number 1 --region us-east-1` shows the public read grant.
- [ ] 8.4 Verify SSM parameters: `aws ssm get-parameter --name /cfn-handler/us-east-1/layer-arn/latest` returns the new ARN; `aws ssm get-parameter --name /cfn-handler/us-east-1/layer-arn/v<version>` returns the same.
- [ ] 8.5 Verify the public discovery surfaces:
   - GH Release body at `https://github.com/igorlg/cfn-handler/releases/tag/v<version>` shows the "Lambda Layer ARNs" table.
   - `curl -fsSL https://github.com/igorlg/cfn-handler/releases/latest/download/layer-arns.json` returns valid JSON with `version`, `layer_name`, `regions` keys.
   - README badge on the GitHub repo page renders the Layer version label correctly.
- [ ] 8.6 Smoke test from a fresh AWS principal (any account): `aws lambda get-layer-version --layer-name <ARN-from-release-table> --region us-east-1` succeeds without `AccessDenied`. Confirms public read.

## 9. Validate + archive

- [x] 9.1 `openspec validate publish-lambda-layer --strict` passes before merging the PR.
- [ ] 9.2 After PR + first release ship: `openspec archive publish-lambda-layer`. The new requirements merge into a fresh `openspec/specs/lambda-layer-publishing/spec.md`.
