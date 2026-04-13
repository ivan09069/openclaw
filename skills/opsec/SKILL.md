# OPSEC Skill

## Purpose
Use this skill for secrets, credentials, sensitive files, and privacy-preserving workflows.

## Core Rules
- Treat private data as private by default
- Never expose secrets in chat, logs, notes, or screenshots
- Redact tokens, API keys, passwords, seed phrases, and private keys
- Distinguish public identifiers from private credentials
- When uncertain whether something is sensitive, treat it as sensitive until confirmed otherwise

## Handling Rules
- Read before moving or editing sensitive files
- Prefer copying to a secure location over destructive cleanup
- Do not print full secret values unless explicitly required
- Do not paste credentials into shared files or long-term notes
- Do not store secrets in MEMORY.md
- Daily memory may reference the existence of a secret artifact, but not the secret itself

## Output Rules
- Prefer summaries, counts, hashes, paths, and classifications
- Show partial values only when needed for identification
- Use redaction for anything reusable as an authenticator

## Execution Rules
1. Identify whether the material is secret, sensitive, or public
2. Minimize exposure
3. Preserve access for Ivan
4. Verify the result without leaking values

## Red Lines
- Never request or reveal seed phrases casually
- Never move or delete credentials without explicit approval
- Never publish or transmit secrets externally without explicit approval

## Completion Standard
A sensitive-data task is complete only when:
- the artifact is accounted for
- exposure is minimized
- access is preserved
- verification is done without leaking the secret
