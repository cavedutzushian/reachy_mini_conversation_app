<!--
Sync Impact Report (temporary; remove before committing)
Version change: unversioned scaffold -> 1.0.0 (initial project-specific constitution)
Modified principles (template slots replaced):
- PRINCIPLE_1_NAME -> I. SDK Compatibility and Existing Architecture
- PRINCIPLE_2_NAME -> II. Minimal, Maintainable Changes
- PRINCIPLE_3_NAME -> III. Reliable Errors and Logging
- PRINCIPLE_4_NAME -> IV. Essential Tests and Quality Gates
- PRINCIPLE_5_NAME -> V. Human Review and Focused Contributions
Added sections: Compatibility and Documentation; Development Workflow and Review
Removed sections: none; placeholder guidance replaced with repository requirements.
Deferred: TODO(RATIFICATION_DATE): maintainer must confirm the original adoption date.
Templates and commands: unchanged; they read this constitution at runtime.
-->
# Reachy Mini Conversation App Constitution

## Core Principles

### I. SDK Compatibility and Existing Architecture

Changes MUST use the Reachy Mini SDK's public API without forking, vendoring, or
monkey-patching its internals, and preserve compatibility when the SDK version changes.
Contributors MUST read affected modules before writing code and match existing structure,
naming, and patterns. Non-trivial changes MUST state design trade-offs before implementation.
Shared realtime behavior MUST remain in `huggingface_realtime.py`. Reuse MUST take precedence
over duplication to keep the application maintainable by its small team.

### II. Minimal, Maintainable Changes

Each PR MUST address one feature or fix with a minimal diff. Code MUST use meaningful names
and contain no dead code, speculative parameters, stubs, redundant wrappers, or single-use
helpers. Comments MUST explain why in one line; docstrings MUST be accurate, one-line
public API descriptions. Public signatures MUST be typed; new code MUST avoid `Any` and
`cast`. Imports MUST be at module scope, attributes MUST be declared rather than probed
for, and obsolete suppressions MUST be removed. Code and explanations MUST make sense
in the merged project without relying on PR history.

### III. Reliable Errors and Logging

Errors MUST NOT be swallowed. Catch the narrowest applicable exception and log it, or
let it propagate where appropriate. Tools MUST log operational failures and return
`{"error": ...}` instead of crashing the conversation loop. New logging MUST use the
module logger with lazy `%`-style arguments; reserve `print` for genuine CLI output.

### IV. Essential Tests and Quality Gates

Tests MUST exercise essential behavior rather than private helpers or implementation
details, and `tests/` MUST mirror `src/`. Bug fixes MUST include regression tests; features
MUST include at least a happy-path test. Proposed test omissions MUST be disclosed for a
human decision. Contributors MUST run the full Ruff, formatting, strict mypy, and pytest
gate before handing work back or requesting review. A failing pipeline MUST NOT be
presented as ready for review; quality MUST NOT be reduced to pass the gate.

### V. Human Review and Focused Contributions

Features and non-trivial changes MUST begin with an issue and agreement on the approach;
small, obvious fixes MAY proceed directly to a PR. AI-assisted contributions MUST be
minimal, readable, and thoughtfully reviewed by a human. Contributors MUST self-review
the diff, answer review comments in their own words, and keep PR descriptions concise.
Agents MUST follow CONTRIBUTING.md's instruction to leave PR creation to the human
and direct that developer to read the contribution guidance first.

## Compatibility and Documentation

- Code MUST support Python 3.10+ and Linux, macOS, and Windows. Hardcoded paths,
  shell-specific commands, and OS-only APIs MUST NOT be introduced without the documented
  fallbacks required by the repository rules.
- PEP 8 and the Google Python Style Guide MUST be followed, including Ruff's 119-character
  line limit, double quotes, and length-sorted imports. New typing MUST use built-in
  generics and `X | None`. PEP 695 syntax, `from __future__ import annotations`, and new
  mypy ignores MUST NOT be introduced. Mypy MUST run in strict mode as configured.
- New dependencies MUST be flagged before addition. Dependency changes MUST include
  `uv lock` and a synchronized `uv.lock`. Secrets and `.env` MUST NOT be committed;
  new configuration variables MUST be documented in `.env.example`.
- Tools MUST follow the existing `Tool`/`ToolDependencies` interface in their own modules,
  with `name`, `description`, `parameters_schema`, and an async dictionary-returning
  `__call__`. Bundled personalities MUST follow existing directories under `profiles/`.
- The root `README.md` MUST remain the documentation source of truth and be updated in
  the same PR when documented behavior, configuration, tools, CLI, or installation changes.
  Additional README files and Markdown files under `docs/` MUST NOT be added. A genuinely
  necessary standalone document MUST be proposed separately in the Reachy Mini SDK docs.
- Architecture changes MUST flag diagram updates in the PR. Diagram changes MUST edit
  `docs/scheme.mmd` and regenerate the SVG; the generated SVG MUST NOT be hand-edited.
- `.github/pull_request_template.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and CI
  workflows MUST NOT be modified unless that modification is the task itself.

## Development Workflow and Review

Contributors MUST search existing issues before filing one and describe expected behavior;
bug reports MUST include reproduction steps, OS, Python version, and relevant debug logs.
Work MUST use `<type>/<issue-number>-<short-description>` branches when an issue exists,
or `<type>/<short-description>` for permitted small fixes without one. Allowed types are
`feat`, `fix`, `docs`, `test`, `refactor`, and `chore`. Commit messages MUST explain the work;
conventional prefixes are optional.

With the environment active, the full local gate is:

```bash
ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v
```

Before review, contributors MUST verify the gate, relevant documentation, dependency lock,
cross-platform compatibility, and absence of secrets. Human authors MUST fill in the
existing PR template without rewriting its structure and manually check applicable boxes.
PR titles MUST explain the work without agent or model names; descriptions MUST state
what changed and why. Maintainers release from `main` by updating the package version,
committing it, and pushing a `v*` tag; existing automation handles releases and HF mirrors.

## Governance

This constitution derives from [AGENTS.md](../../AGENTS.md) and
[CONTRIBUTING.md](../../CONTRIBUTING.md); it MUST NOT replace or weaken their requirements.
Their detailed rules remain applicable during specification, planning, implementation,
and review. Amendments MUST identify their rationale, source-rule alignment, and impact
for human review through the existing contribution process. Specifications, plans, tasks,
and PR reviews MUST check compliance; conflicts MUST be resolved before implementation
or review proceeds.

Constitution versions MUST use semantic versioning: MAJOR for incompatible principle
removals or redefinitions, MINOR for new principles or materially expanded guidance, and
PATCH for non-semantic clarifications. Amendments MUST update the version and amendment
date while preserving the original ratification date once confirmed.

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE): confirm original adoption date | **Last Amended**: 2026-10-28
