# Roadmap

This document captures the directional thinking for `cfn-handler`'s
post-1.x evolution. It's not a commitment — items move freely between
sections as priorities shift.

OpenSpec changes are the canonical, executable plan. This roadmap is the
*context* those changes live in.

---

## Vision

`cfn-handler` is a small, focused, zero-dependency library for writing
CloudFormation Custom Resource Lambda handlers. The library does the
boilerplate (lifecycle dispatch, presigned-URL response, polling via
EventBridge, response-status handling) so users focus on the resource
logic.

The library is **not** a framework. It does not own the user's logging
stack, idempotency layer, type system, or deployment toolchain. It
*interoperates* — cleanly — with whatever the user already runs.

---

## Non-goals

These have been considered and explicitly declined. Listed here so we
don't re-litigate them.

- **CDK construct library** — `aws-cdk.custom-resources.Provider` already
  occupies that niche, and the audience overlap (CDK + Python + custom
  resources + cfn-handler) is small. SAM/raw-CFN is the consumer
  identity.
- **Step Functions / "Durable" orchestration for >15 min runs** — a
  non-problem. Polling already re-invokes the Lambda via EventBridge
  scheduled rules; the actual ceiling is the CFN per-resource timeout
  and the response-URL TTL, both well above 15 minutes.
- **CloudFormation macros / Transforms** — antipattern. Account-global
  registration, hard to debug, requires `CAPABILITY_AUTO_EXPAND`. The
  modern alternative (CFN Resource Type Registry) is parked separately
  below.
- **Async/await handlers** — `async def on_create(...)` would let users
  use async SDKs natively, but most CFN custom resources are I/O-light.
  Park unless users ask.
- **CDK usage docs** — same reasoning as the construct library. Audience
  too small to justify maintenance overhead. Users who need to call
  `cfn-handler` from a CDK-deployed Lambda will figure out the obvious
  shape.

---

## Active priorities (next 3–6 months)

These are scoped, designed, and ready to (or already) ship. Each becomes
its own OpenSpec change.

### 1. ~~Testing helpers~~ — shipped in `v1.3.0`

Shipped as `cfn_handler.testing`: `replay()`, `Replay` dataclass,
`make_event` / `make_context` factories, `assert_success` / `assert_failed`
/ `assert_deferred` helpers, and pytest fixtures auto-discovered via the
`pytest11` entry point. The legacy `test_mode` / `last_response` surface
is soft-deprecated (DeprecationWarning) and scheduled for removal in v2.0.

See: archived OpenSpec change `add-testing-helpers` (search
`openspec/changes/archive/`) and the `testing-helpers` capability spec.

### 2. Better logging — likely `v1.4.0`

**Shape**:
- A stdlib `logging.Filter` that injects CFN context fields
  (`StackId`, `LogicalResourceId`, `RequestId`, `RequestType`) into
  every log record produced during a flow. Works with any logger.
- A `setup_logging()` opt-in convenience that attaches a JSON formatter
  and the context filter to the `cfn_handler` logger.
- Internal lifecycle state-transition logs at INFO:
  `dispatching:create → handler:returned → response:sent`.

**Powertools interop**: the context filter is a plain `logging.Filter`;
Powertools users `.addFilter()` it on the Powertools `Logger`. No
Powertools dep. Document the recipe.

### 3. Optional idempotency module — likely `v1.5.0`

**Shape**:
- New module `cfn_handler.idempotency` (importable but not in `__all__`).
- Pluggable backend protocol; the user provides their own DynamoDB
  table, S3 bucket, or in-memory cache (the last useful only for
  testing).
- Usage: `@resource.idempotent(backend=...)` wrapping `@resource.create`
  etc. Caches the response keyed by `RequestId`; on re-invocation
  with the same `RequestId`, replays the cached response.

**Powertools interop**: ship a thin adapter that wraps Powertools'
`@idempotent` so users with that already wired don't need a second
backend.

**No hard dep on Powertools.**

---

## Future / unscoped

Ideas worth doing, not yet ready.

### Typed events — `v2.0` candidate

`event: dict[str, Any]` everywhere is an anti-pattern given the project's
"Rust-style error handling" stance. Concrete plan when we get there:

- `cfn_handler.events` module with `CreateEvent`, `UpdateEvent`,
  `DeleteEvent` `TypedDict` definitions covering the documented CFN
  custom-resource event shape.
- Handler decorators preserve the existing `event: dict[str, Any]`
  signature for backwards compatibility, **and** accept handlers typed
  with the new TypedDicts via overloads.
- Powertools interop: structural compatibility with
  `aws_lambda_powertools.utilities.parser.models.CloudFormationCustomResourceEvent`
  (pydantic model) — both should satisfy the same `Mapping`-shaped
  protocol so users can mix-and-match without runtime cost.

This is a breaking change to the `__all__` surface, hence v2.0.

### CFN Resource Type Registry support

The modern CFN private registry mechanism (`AWS::CloudFormation::Resource`)
lets you publish a resource type with a JSON schema, consumed in templates
as `MyOrg::MyService::MyResource`. It overlaps with what `cfn-handler`
does today (Lambda-backed custom resources) but the deployment surface
and user experience are very different:

- Resource Types are deployed via the CFN registry, not as Lambda
  functions in the user's account.
- Schema-validated input/output.
- Versioning is handled by CFN, not the consumer.

Worth a real exploration session before committing — this is arguably a
*different product* than `cfn-handler` is today, and might be more sensibly
shipped as a separate library that shares no code with the runtime.

**Status**: parked, low priority, requires research spike.

---

## Parallel-track work

### `cfn-lint-cfn-handler` plugin (separate repo)

A cfn-lint rule plugin catching `cfn-handler`-specific misconfigurations
(Lambda timeout too low, polling-using handler missing IAM permissions,
wrong-region layer ARN against our published manifest).

Lives in its own GitHub repo (`cfn-lint-cfn-handler`) for release-cadence
independence. Bootstrap context for that repo is in
`tmp/cfn-lint-plugin-bootstrap.md` (will be deleted once the new repo is
live).

The headline rule is **W9105: cfn-handler layer ARN doesn't match the
deployment region**. It consumes the `layer-arns.json` manifest published
with every `cfn-handler` release. No-one else can write that rule.

---

## Decision log

Things we considered and decided about, kept here for future reference.

| Decision                                                | Date       | Rationale                                                                                       |
|---------------------------------------------------------|------------|-------------------------------------------------------------------------------------------------|
| Skip CDK construct                                       | 2026-05-22 | `aws-cdk.custom-resources.Provider` covers it; audience overlap with cfn-handler users is small |
| Drop SFN/Durable for long-running ops                    | 2026-05-22 | Polling already re-invokes via EventBridge; 15 min Lambda limit is not the actual ceiling       |
| Hard-pass on CFN macros                                  | 2026-05-22 | Account-global, hard to debug, `CAPABILITY_AUTO_EXPAND` ergonomics                              |
| cfn-lint plugin in separate repo (not monorepo)          | 2026-05-22 | Independent versioning, simpler CI, avoids workspace-restructure overhead                       |
| Powertools interop via duck-typing, never as a hard dep  | 2026-05-22 | Zero-dep posture is core; Powertools users get free interop, non-Powertools users unaffected    |
| Testing helpers ship before logging improvements         | 2026-05-22 | Motivation; testing surface design might inform logging surface design                          |

---

## Updating this document

- New idea? Add it under "Future / unscoped" with a one-paragraph shape.
- Idea picked up for work? Move to "Active priorities" with a target version.
- Idea declined? Move to "Non-goals" or the "Decision log" with rationale.
- Idea shipped? Delete from this doc; the OpenSpec spec captures the
  durable contract.
