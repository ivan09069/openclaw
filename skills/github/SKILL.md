# GitHub Skill

## Purpose
Use this skill for repositories, issues, pull requests, gists, releases, workflows, and contribution-grade changes.

## Core Rules
- Inspect before editing
- Prefer the smallest viable patch
- Explain blast radius before risky changes
- Keep changes auditable
- Prefer diffable outputs over vague summaries

## Working Style
1. Identify repo state
2. Read the relevant files
3. Change the smallest surface area
4. Verify with readback, diff, or tests
5. Summarize what changed and why

## Safe Defaults
- Prefer read-only inspection first
- Prefer targeted edits over full rewrites
- Prefer patching config rather than reshaping the whole repo
- Keep generated artifacts separate from source when practical

## Repo Inspection
Before making changes, check:
- current branch
- git status
- relevant files
- workflow files if CI is involved
- package manager / build system in use

## PR and Review Rules
- Summarize intent in plain language
- Call out risk areas clearly
- Separate mechanical edits from semantic edits
- For dependency bumps, note version jump and likely break surface
- For CI changes, state exactly what behavior changes

## Releases and Artifacts
- Tag only when explicitly asked
- Prefer reproducible build outputs
- Keep notes concise and factual
- Include proof of what was built or verified

## Completion Standard
A GitHub task is complete only when:
- the target scope is clear
- the changed files are known
- the result is verified with readback, diff, or test output
- the risk surface is stated
