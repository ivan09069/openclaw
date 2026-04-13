# Fix OpenClaw

## Goal
Stabilize core workspace files and verify they exist.

## Commands
```bash
cd ~/.openclaw/workspace
ls -l AGENTS.md SOUL.md USER.md TOOLS.md IDENTITY.md MEMORY.md HEARTBEAT.md RULES.md PROJECTS.md
find skills -maxdepth 2 -type f | sort
find memory -maxdepth 1 -type f | sort
