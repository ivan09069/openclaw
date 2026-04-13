# Termux Skill

## Purpose
Use this skill for work inside Ivan's Android Termux environment.

## Environment Defaults
- Default root: `~`
- Preferred workspace root: `~/.openclaw/workspace`
- Prefer `~/...` paths over long absolute paths unless precision matters
- Assume mobile copy/paste workflow
- Keep commands fat-finger tolerant

## Operating Rules
- Prefer one-shot scripts over scaffolds
- Prefer exact commands over vague instructions
- Create parent directories with `mkdir -p`
- Read before editing
- Back up before major edits
- Verify every write immediately
- Use append/patch before full rewrite when practical
- Avoid destructive actions unless explicitly approved

## Verification Pattern
After writes, verify with one or more of:
- `ls -l <file>`
- `sed -n '1,120p' <file>`
- `sha256sum <file>`
- `grep -n 'pattern' <file>`

## Execution Pattern
1. `cd` into the correct directory
2. create needed directories
3. write the smallest useful artifact
4. read it back
5. record durable facts if needed

## Anti-Loop Rule
If the same command path fails twice:
- stop retrying the same approach
- switch strategy

## Android/Termux Caveats
- Some native/vector packages may be unsupported on android-aarch64
- Shebang/path issues can appear with node/python wrappers
- Clipboard-driven workflows are less reliable than direct file writes
- Prefer plain text outputs and markdown notes over fancy local dependencies

## Completion Standard
A task is not complete until there is proof:
- saved file
- readback output
- diff
- test result
- exact rerun command
