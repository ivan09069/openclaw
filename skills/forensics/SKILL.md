# Forensics Skill

## Purpose
Use this skill for artifact triage, evidence preservation, recovery analysis, wallet-related scanning, and incident-style file investigation.

## Core Rules
- Forensic-first
- Read-only by default
- Preserve evidence before transforming it
- Do not overclaim beyond the evidence
- Prefer reproducible outputs

## Evidence Handling
- Keep source paths
- Hash important artifacts when practical
- Separate raw evidence from derived outputs
- Write summaries and machine-readable outputs
- Preserve timestamps when possible

## Investigation Workflow
1. Define the target artifact class
2. Scan and collect candidates
3. Score or classify them
4. Preserve the strongest candidates
5. Write a concise evidence summary
6. Keep raw and derived outputs separate

## Output Structure
Preferred output set:
- summary.txt or summary.md
- manifest.tsv or manifest.csv
- hashes.txt when practical
- quarantine or evidence directory for preserved artifacts
- logs for scan scope and exclusions

## Claims Discipline
- State what was found
- State what was not found
- Separate evidence from inference
- Mark uncertainty explicitly
- Do not claim compromise, recovery, or ownership without support

## Safety Rules
- Do not modify originals unless explicitly requested
- Do not destroy evidence
- Do not mix private secrets into public summaries
- Keep sensitive findings minimally exposed

## Completion Standard
A forensic task is complete only when:
- evidence is preserved
- outputs are structured
- claims match the evidence
- another pass can reproduce the result
