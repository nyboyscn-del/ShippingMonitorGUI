# Project Status

## Delivery Baseline

Current sealed trial package available in the local workspace (delivery artifact; not versioned):

```text
release\ShippingMonitorGUI_v1.0_trial20260521.zip
```

The extracted trial package directory currently present in the local workspace is:

```text
release\ShippingMonitorGUI_v1.0_trial
```

## Entry Points

- Current official GUI entry point: `src\gui_main.py`
- Legacy CLI / Stage1 entry point: `src\main.py`

`src\main.py` is not the current formal GUI entry point.

## Security And Packaging Rules

- Authorization private keys are forbidden from being committed.
- `tools\license_keys\`, `tools\issued_licenses.csv`, and `*.pem` files must stay out of version control and customer packages.
- Generated authorization state such as `config\license_state.json` and `config\license_state*.json` must not be shipped as initial customer state.
- Legacy `config\license.json` must not be included in formal customer packages unless a future delivery decision explicitly changes this rule.

## Customer Config Baseline

The initial customer package `config` directory should only keep:

- `config.json`
- `config.example.json`

Runtime authorization state may be generated locally after activation.

## Known Pending Items

- Camera barcode recognition is pending upgrade. The current implementation and UI status keep this feature conservative because `pyzbar` and native barcode runtime dependencies can be unstable across machines.
- FFmpeg should be completed and verified before formal delivery. This is recommended for reliable MP4 export and broader playback compatibility.

## Current Governance Files

This project now includes root-level governance files:

- `README.md`
- `requirements.txt`
- `.gitignore`
- `PROJECT_STATUS.md`
- `CONTRIBUTING.md`

## Source Control Baseline

- Canonical remote: `https://github.com/nyboyscn-del/ShippingMonitorGUI` (public release)
- Maintained branch: `main`
- The versioned baseline contains source, documentation, and blank templates. Runtime configuration, authorization data, private keys, issued-license records, customer data, local evidence, backups, and generated binaries stay outside Git.
- Follow `CONTRIBUTING.md` for routine sync, branch, review, and commit steps.

