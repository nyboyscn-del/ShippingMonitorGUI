# Maintenance workflow

## Source of truth

The GitHub repository `nyboyscn-del/ShippingMonitorGUI` is the versioned source baseline for the public release.

The `main` branch is the maintained baseline. Keep `README.md` and `PROJECT_STATUS.md` aligned with the supported entry point, package behavior, and known limitations.

## Routine update

1. Update the local baseline before starting work:

   ```powershell
   git switch main
   git pull --ff-only
   ```

2. Make each maintenance change on a focused branch:

   ```powershell
   git switch -c fix/short-description
   ```

3. Review `git status` and `git diff` before committing. Stage only intended source and documentation files.
4. Use a short commit message that describes the change, then push the branch:

   ```powershell
   git add <intended-files>
   git commit -m "Describe the change"
   git push -u origin fix/short-description
   ```

5. Merge reviewed work into `main`, then update local `main` with `git pull --ff-only`.

## Files that stay local

Do not commit local runtime configuration, activation/license data or keys, issued-license records, customer records, recordings, logs, evidence captures, recovery backups, downloaded FFmpeg binaries, or generated build/release packages. `config/config.example.json` is the tracked configuration template; the application creates a local `config/config.json` from it when needed.

Keep release packages as separate delivery artifacts. The repository is a source backup and maintenance history, not a distribution channel for customer data or authorization material.
