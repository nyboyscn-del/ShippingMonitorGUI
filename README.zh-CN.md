# ShippingMonitorGUI

[English](README.md) | **简体中文**

发货录像监控 · 条码触发录像 · 回放查询 · 局域网查询 · 离线授权

ShippingMonitorGUI 是一个 Windows 桌面工具，用于发货视频监控、条码触发录像、录像回放/查询，以及离线授权。

## 下载

免安装的 Windows 成品包：

- **GitHub Releases（正式来源）：** [v1.0.0](https://github.com/nyboyscn-del/ShippingMonitorGUI/releases/tag/v1.0.0) — 下载 `ShippingMonitorGUI_v1.0.0.zip`，解压后运行 `ShippingMonitorGUI\ShippingMonitorGUI.exe`。
- **GitCode 国内镜像：** [发行版](https://gitcode.com/nyboys/ShippingMonitorGUI/releases) — 同一个安装包，核验后在镜像侧单独发布。
- `ShippingMonitorGUI_v1.0.0.zip` 的 SHA256：`524f41e4b75a9c408ea971d62ab75bc557b9aa258aabc257c3196cd4a7cd54ba`

## 当前入口

当前正式的 GUI 入口是：

```bat
python src\gui_main.py
```

GUI 开发、冒烟检查、打包验证和面向客户的操作，都以这个入口为准。

## 旧版 Stage1 入口

`src\main.py` 是旧的 CLI / Stage1 入口，仅为历史参考和早期命令行流程的兼容而保留，不是当前正式的 GUI 入口。

## 配置

运行时配置位于 `config` 目录下。

面向客户的安装包，初始 `config` 目录应只保留：

- `config.json`
- `config.example.json`

不要把本地授权状态或旧的授权文件打进客户初始包。

## 依赖

从以下文件安装运行时与打包依赖：

```bat
pip install -r requirements.txt
```

`pyzbar` 为可选依赖。摄像头条码识别目前标记为待升级，正式使用前可能需要额外的原生 DLL/运行时准备。

## 打包说明

已发布的 v1.0.0 安装包由本公开源码经 `build_exe.bat` 构建，经 GitHub Releases（及 GitCode 镜像）分发。它取代了早期由私有代码树构建的封存试用包 `release\ShippingMonitorGUI_v1.0_trial20260521.zip`，该试用包不对外发布。

授权私钥、已生成的授权状态、已签发的授权记录和 PEM 文件，不得提交到仓库，也不得打进客户包。

建议在正式交付前完成并验证 FFmpeg 支持，以保证 AVI 转 MP4 导出和回放在客户机器上的兼容性可预期。

## 授权

本项目采用双授权模式，完整条款见 [LICENSE](LICENSE)：

- **个人与非商业使用：免费。** 可以使用、复制和修改源代码。
- **商业使用：需要付费授权。** 在企业或个体经营活动中使用、集成进对外销售/收费的产品或服务、或基于本软件向第三方收费提供服务，都属于商业使用，请先联系作者取得书面授权：izchclaw@qq.com

本项目为源码开放（source-available），不是 OSI 批准的开源许可证。

## 镜像与维护

- **主仓：** 本 GitHub 仓库（https://github.com/nyboyscn-del/ShippingMonitorGUI）。以 `main` 为基线，维护改动走短生命周期分支。更新与评审步骤见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- **国内镜像：** [gitcode.com/nyboys/ShippingMonitorGUI](https://gitcode.com/nyboys/ShippingMonitorGUI)，供国内更快访问，并作为华为码道 CodeArts 的维护入口。镜像同步与主仓相同的代码（分支、标签与提交）和 [LICENSE](LICENSE)，不是另一个项目；发布版本以 GitHub 为正式来源，GitCode 侧的安装包在核验后单独发布。
- **问题反馈：** GitHub 与 GitCode 任一平台都可以提 Issue，维护方会合并处理，请只在一处提交，不要两边重复提。
- **商用授权：** 不走任一平台的私信，只走邮箱：izchclaw@qq.com

只有源码、维护文档和空白模板属于 Git 管理范围。本地 `config/config.json`、授权/许可材料、客户数据、日志、录像、恢复备份、FFmpeg 二进制文件以及生成的构建/发布包均已排除。程序会在需要时从 `config/config.example.json` 创建 `config/config.json`。
