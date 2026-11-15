# ShippingMonitorGUI

**English** | [简体中文](README.zh-CN.md)

发货录像监控 · 条码触发录像 · 回放查询 · 局域网查询 · 离线授权

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

## Mirror & Maintenance / 镜像与维护

- **Canonical repository / 主仓:** this [GitHub repository](https://github.com/nyboyscn-del/ShippingMonitorGUI). `main` is the baseline; make maintenance changes on short-lived branches. See [CONTRIBUTING.md](CONTRIBUTING.md) for the update and review steps.
- **GitCode (AtomGit) mirror / 国内镜像:** [gitcode.com/nyboys/ShippingMonitorGUI](https://gitcode.com/nyboys/ShippingMonitorGUI) — a sync mirror for faster access in mainland China and as the maintenance entry point for Huawei CodeArts (码道). The mirror syncs the same code (branches, tags, and commits) and the same [LICENSE](LICENSE); it is not a separate project. Releases are published from GitHub as the canonical source; GitCode release packages are published separately after verification.
- **Issues:** may be filed on either platform; maintainers triage and mirror them, so please file in one place only.
- **Commercial licensing / 商用授权:** not handled via platform messages on either site — contact the author by email only: izchclaw@qq.com

本项目主仓在 GitHub，GitCode（AtomGit）镜像仅作国内同步与码道维护入口，两边代码与授权保持一致，发布版本以 GitHub 为准、GitCode 侧单独核验发布；问题在任一平台提一次即可，商用授权只走邮箱联系。

Only source, maintenance documentation, and blank templates belong in Git. Local `config/config.json`, authorization/license material, customer data, logs, recordings, recovery backups, FFmpeg binaries, and generated build/release packages are excluded. The application creates `config/config.json` from `config/config.example.json` when needed.

