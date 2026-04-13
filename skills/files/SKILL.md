# Files Skill

## Purpose
Use this skill for locating, organizing, deduplicating, labeling, quarantining, and summarizing files.

## Core Rules
- Read-only and reversible by default
- Prefer quarantine, rename, move, or manifest over deletion
- Preserve original paths and metadata when possible
- Record what changed

## Working Style
- Search first
- Classify second
- Change third
- Verify fourth
- Summarize last

## Safe Operations
- `find` for discovery
- `grep` for text search
- `sha256sum` for content identity
- `ls -l` and `stat` for metadata
- move to named folders instead of deleting
- write TSV, CSV, or markdown manifests for actions taken

## Required Metadata for File Actions
When moving, quarantining, or deduplicating, capture:
- original path
- new path
- sha256 if practical
- size
- timestamp
- reason for action

## Deduping Rules
- Never assume same filename means same content
- Prefer hash-based grouping
- Keep the newest or most authoritative copy only after verification
- Produce a keep/remove manifest before destructive action
- Do not delete by default

## Organization Rules
- Use clear folder names
- Prefer human-readable labels
- Avoid ambiguous quarantine names
- Keep a summary file in the output directory

## Completion Standard
A file task is complete only when:
- the file set is verified
- actions are reversible when possible
- a manifest or summary exists
- the result can be rerun or audited
