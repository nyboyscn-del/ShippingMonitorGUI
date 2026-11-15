# ShippingMonitorGUI

ShippingMonitorGUI is a Windows desktop tool for shipping video monitoring, barcode-triggered recording, playback/query, and offline authorization.

## Current Entry Point

The current official GUI entry point is:

```bat
python src\gui_main.py
```

Use this entry point for current GUI development, smoke checks, packaging verification, and customer-facing operation.

## Legacy Stage1 Entry Point

`src\main.py` is the old CLI / Stage1 entry point. It is retained for historical reference and compatibility with early-stage command-line workflows, but it is not the current official GUI entry point.

## Configuration

Runtime configuration lives under `config`.

For customer packages, the initial `config` directory should only keep:

- `config.json`
- `config.example.json`

Do not ship local authorization state or legacy license files in the initial customer package.

## Dependencies

Install runtime and packaging dependencies from:

```bat
pip install -r requirements.txt
```

`pyzbar` is optional. Camera barcode recognition is currently marked as pending upgrade and may require additional native DLL/runtime preparation before production use.

## Packaging Notes

The current sealed trial package is:

```text
release\ShippingMonitorGUI_v1.0_trial20260521.zip
```

Authorization private keys, generated license state, issued license records, and PEM files must not be committed or included in customer packages.

FFmpeg support is recommended to be completed and verified before formal delivery so AVI-to-MP4 export and playback compatibility are predictable on customer machines.

## License / 授权

本项目采用双授权模式，完整条款见 [LICENSE](LICENSE)：

- **个人与非商业使用：免费。** 可以使用、复制和修改源代码。
- **商业使用：需要付费授权。** 在企业或个体经营活动中使用、集成进对外销售/收费的产品或服务、或基于本软件向第三方收费提供服务，都属于商业使用，请先联系作者取得书面授权：izchclaw@qq.com

This project is source-available under a dual license (see [LICENSE](LICENSE)): free for personal and non-commercial use; commercial use requires a paid license from the author (izchclaw@qq.com). It is not an OSI-approved open-source license.

## Version Control And Maintenance

The maintained source baseline is this [GitHub repository](https://github.com/nyboyscn-del/ShippingMonitorGUI). Use `main` as the baseline and make maintenance changes on short-lived branches. See [CONTRIBUTING.md](CONTRIBUTING.md) for the update and review steps.

Only source, maintenance documentation, and blank templates belong in Git. Local `config/config.json`, authorization/license material, customer data, logs, recordings, recovery backups, FFmpeg binaries, and generated build/release packages are excluded. The application creates `config/config.json` from `config/config.example.json` when needed.

