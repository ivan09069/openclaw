# Docs Skill

## Purpose
Use this skill for specifications, runbooks, architecture notes, audits, proposals, and decision records.

## Core Rules
- Decision-first structure
- State assumptions explicitly
- Separate facts, inferences, and open questions
- Define success and failure conditions
- Prefer precise wording over decorative wording

## Default Structure
When writing a technical document, prefer:
1. Purpose
2. Scope
3. Assumptions
4. Constraints
5. Decision or design
6. Risks
7. Verification or acceptance criteria
8. Open questions

## Writing Rules
- Keep sections tight
- Prefer bullets over long paragraphs when operational
- Use exact names, paths, and versions when relevant
- Avoid hand-wavy claims
- Mark uncertainty explicitly

## Runbook Rules
A runbook should contain:
- exact commands
- expected outputs or checks
- branching only on real failure points
- recovery or rollback notes when relevant

## Spec Rules
A spec should define:
- what is being changed
- what is not being changed
- invariants that must hold
- validation method
- failure conditions

## Audit Rules
An audit should distinguish:
- confirmed findings
- probable findings
- missing evidence
- recommendations
- priority or severity where applicable

## Completion Standard
A docs task is complete only when:
- the document has a clear purpose
- assumptions and constraints are explicit
- verification criteria exist
- another person could act on it without guessing
