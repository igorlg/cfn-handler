#!/usr/bin/env node
//
// Local validator for release-please's `uv.lock` updater.
//
// Why this exists:
// release-please's TOML updater for the `extra-files` mechanism uses
// jsonpath-plus over an internal AST shape that exposes string nodes as
// `{value, kind}` rather than bare strings. The bare jsonpath
// `@.name=='cfn-handler'` therefore does not match — see
// https://github.com/googleapis/release-please/issues/2455. The working
// form requires `.value`: `@.name.value=='cfn-handler'`. PR #2693 may
// eventually drop this requirement; until then, this script is the
// safety net.
//
// Why local validation matters:
// the `GenericToml` class's docstring says "the parser does reformat
// the document and removes all comments". That is misleading — reading
// `util/toml-edit.js` shows the parser is only used to locate the byte
// range of the target value via a custom TaggedTOMLParser, after which
// the replacement is a surgical `input.slice(0, start) + new + input.slice(end)`.
// If the docstring had been correct, our extra-files approach would be a
// disaster (1872-line uv.lock rewrites every release). It isn't, but
// "trust but verify" — this script keeps that verification automated.
//
// What this checks:
// 1. POSITIVE: our jsonpath (with `.value`) finds the cfn-handler
//    self-version entry and only that entry.
// 2. NEGATIVE: the bare jsonpath (without `.value`) finds nothing,
//    confirming the workaround is necessary and our spec rationale holds.
// 3. INVARIANT: the updater touches exactly one line and zero non-target
//    bytes. If release-please ever changes to re-serialize, this will
//    fail loudly.
//
// Version pinning:
// `package.json` pins `release-please` to the exact version bundled in
// the action SHA pinned in `.github/workflows/release.yml`. When you
// bump the action SHA, also bump this pin and re-run this script.
// See README.md for the linkage.
//
// Usage:
//   cd tests/release-please && npm install && node validate-uv-lock-updater.js
//

const fs = require("node:fs");
const path = require("node:path");
const process = require("node:process");

const { GenericToml } = require("release-please/build/src/updaters/generic-toml.js");
const { Version } = require("release-please/build/src/version.js");

// Repo paths. This script lives at <repo>/tests/release-please/.
const SCRIPT_DIR = __dirname;
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..", "..");
const LOCK_PATH = path.join(REPO_ROOT, "uv.lock");
const CONFIG_PATH = path.join(REPO_ROOT, "release-please-config.json");

// Synthetic version for the dry-run replacement. Same length as common
// real versions so byte-count math stays exact.
const SYNTHETIC_VERSION = "9.9.9";

// Silent logger for the negative test (we expect a "no entries modified"
// warning and don't want it printed during normal runs).
const SILENT_LOGGER = {
  warn: () => {},
  error: () => {},
  info: () => {},
  debug: () => {},
};

/**
 * Apply a jsonpath update against the real uv.lock and return the diff stats.
 * @param {string} jsonpath
 * @param {{ silent?: boolean }} opts
 */
function tryUpdate(jsonpath, opts = {}) {
  const original = fs.readFileSync(LOCK_PATH, "utf8");
  const updater = new GenericToml(jsonpath, Version.parse(SYNTHETIC_VERSION));
  const updated = opts.silent
    ? updater.updateContent(original, SILENT_LOGGER)
    : updater.updateContent(original);

  const origLines = original.split("\n");
  const newLines = updated.split("\n");
  const lineCountChanged = origLines.length !== newLines.length;
  const changedLines = [];
  if (!lineCountChanged) {
    for (let i = 0; i < origLines.length; i++) {
      if (origLines[i] !== newLines[i]) {
        changedLines.push({ lineNumber: i + 1, before: origLines[i], after: newLines[i] });
      }
    }
  }
  return {
    matched: updated !== original,
    lineCountChanged,
    changedLines,
    byteDelta: updated.length - original.length,
  };
}

/**
 * Read the `extra-files` block for the cfn-handler package out of the
 * release-please config so this test stays in lockstep with the real
 * config. If the config block is removed or renamed, the test fails
 * loudly rather than silently testing a stale path.
 */
function readConfiguredJsonpath() {
  const config = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
  const pkg = config.packages?.["."];
  if (!pkg) {
    throw new Error(`release-please-config.json: packages["."] not found`);
  }
  const extraFiles = pkg["extra-files"];
  if (!Array.isArray(extraFiles) || extraFiles.length === 0) {
    throw new Error(
      `release-please-config.json: packages["."]["extra-files"] missing or empty. ` +
        `If you removed the uv.lock sync, also remove this validator.`,
    );
  }
  const uvLockEntry = extraFiles.find(
    (entry) => entry.path === "uv.lock" && entry.type === "toml",
  );
  if (!uvLockEntry) {
    throw new Error(
      `release-please-config.json: no extra-files entry with path="uv.lock" type="toml" found`,
    );
  }
  if (!uvLockEntry.jsonpath) {
    throw new Error(`release-please-config.json: uv.lock extra-files entry missing jsonpath`);
  }
  return uvLockEntry.jsonpath;
}

let failures = 0;

function check(label, predicate, detail) {
  const ok = predicate();
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}`);
  if (!ok) {
    failures += 1;
    if (detail) console.log(`      ${detail}`);
  }
}

// -----------------------------------------------------------------------
// Positive test: our configured jsonpath updates exactly one line.
// -----------------------------------------------------------------------

const configuredJsonpath = readConfiguredJsonpath();
console.log(`Configured jsonpath: ${configuredJsonpath}`);
console.log("");

const positive = tryUpdate(configuredJsonpath);

console.log("Positive test (our jsonpath SHOULD update uv.lock):");
check(
  "  jsonpath matches the cfn-handler self-version entry",
  () => positive.matched,
  "the configured jsonpath did not match anything in uv.lock; check `release-please-config.json` and the upstream issue list at the top of this script",
);
check(
  "  line count is preserved (no whole-file rewrite)",
  () => !positive.lineCountChanged,
  "the updater changed the line count; release-please may have re-serialized the file (check the GenericToml docstring vs. its implementation)",
);
check(
  "  exactly one line changed",
  () => positive.changedLines.length === 1,
  `expected 1 changed line, got ${positive.changedLines.length}`,
);
if (positive.changedLines.length === 1) {
  const { lineNumber, before, after } = positive.changedLines[0];
  console.log(`        Line ${lineNumber}:`);
  console.log(`          - ${before}`);
  console.log(`          + ${after}`);
  check(
    "  changed line is the cfn-handler self-version entry",
    () =>
      before.trim().startsWith("version = ") &&
      after.trim() === `version = "${SYNTHETIC_VERSION}"`,
    `got: before=${JSON.stringify(before)}, after=${JSON.stringify(after)}`,
  );
}
check(
  "  byte delta is consistent with the version-string swap",
  () => Math.abs(positive.byteDelta) < 8,
  `byte delta was ${positive.byteDelta}; suggests something larger than the version field changed`,
);

console.log("");

// -----------------------------------------------------------------------
// Negative test: the bare jsonpath (without `.value`) does NOT match.
// This is the bug from googleapis/release-please#2455. If this ever
// starts passing, upstream PR #2693 has likely landed and we can drop
// `.value` from the jsonpath.
// -----------------------------------------------------------------------

const bareJsonpath = "$.package[?(@.name=='cfn-handler')].version";
const negative = tryUpdate(bareJsonpath, { silent: true });

console.log("Negative test (bare @.name jsonpath SHOULD fail to match):");
check(
  "  bare jsonpath does NOT match (the bug from #2455 is still present)",
  () => !negative.matched,
  "the bare jsonpath now matches — upstream PR #2693 may have landed. Re-validate the workaround necessity and consider simplifying release-please-config.json.",
);

console.log("");
if (failures === 0) {
  console.log("All checks passed. release-please will surgically update uv.lock on release.");
  process.exit(0);
} else {
  console.error(`${failures} check(s) failed. See output above for details.`);
  process.exit(1);
}
