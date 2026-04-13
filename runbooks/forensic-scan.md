# Forensic Scan

## Goal
Run a reversible, evidence-first scan workflow.

## Commands
OUT="$HOME/storage/downloads/forensic_scan_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
find "$HOME" -type f 2>/dev/null | sed -n '1,500p' > "$OUT/file_sample.txt"
printf "scan_root\t%s\n" "$HOME" > "$OUT/summary.tsv"
printf "output_dir\t%s\n" "$OUT" >> "$OUT/summary.tsv"
ls -l "$OUT"

## Verify
- output directory exists
- `file_sample.txt` exists
- `summary.tsv` exists

## Notes
- read-only by default
- preserve source paths
- add hashes/manifests before any movement or quarantine
