# AstrBot 豪华网易云点歌插件

[![version](https://img.shields.io/badge/version-1.2.0-blue.svg)](https://github.com/NachoCrazy/netease-music-astrbot-plugin)
[![license](https://img.shields.io/github/license/NachoCrazy/netease-music-astrbot-plugin.svg)](LICENSE)

这是一款为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的，功能强大且体验豪华的网易云音乐点歌插件。

## ✨ 功能亮点

- **交互式点歌**：通过关键词搜索歌曲，机器人会返回一个列表供您选择。
- **豪华信息卡片**：播放时，会发送包含**歌曲封面**、**详细信息**（歌名、歌手、专辑、时长）的精美图文卡片。
- **语音播放**：直接发送可播放的语音消息，在聊天窗口即可享受音乐。
- **智能音质回退**：当您设定的最高音质不可用时（如VIP限制），插件会自动尝试获取次一级音质，大大提高播放成功率。
- **多种触发方式**：支持命令（如 `/点歌`）和自然语言（如 `来一首...`）两种方式点歌。
- **WebUI配置**：可在 AstrBot 的网页后台轻松配置各项参数。

## ⚙️ 安装与配置

### 依赖

本插件依赖一个外部的 **Netease Cloud Music API (增强版)** 服务。请您务必先根据其文档自行部署该服务。

- **API 仓库地址**: [https://github.com/neteasecloudmusicapienhanced/api-enhanced](https://github.com/neteasecloudmusicapienhanced/api-enhanced)

推荐的部署方式是使用 Docker。

### 安装

1. 在 AstrBot 的插件商店中搜索 `netease_music_enhanced` 并安装。
2. 或者，直接将本项目克隆到您的 AstrBot `data/plugins` 目录下。

### 配置

安装并重启 AstrBot 后，在网页后台的 **插件配置** -> **`netease_music_enhanced`** 中进行设置：

1. **网易云API地址**：填写您部署的 API 服务的地址（例如 `http://127.0.0.1:3000`）。
2. **默认音质**：选择您希望优先播放的音质。
3. **搜索结果数量**：设置每次搜索返回的歌曲数量。

### 音质等级与中文显示

「优先音质」使用下拉选择，显示中文名称、客户端英文名称及参考规格；保存和请求 API 时使用原有英文代码，兼容旧配置。代码层同时识别中文名称、API 代码以及 HQ、SQ、Master 等展示名称。不提供单独的手动覆盖输入框。

| 中文名称 | 展示名称 | API 代码 | 参考规格 |
| --- | --- | --- | --- |
| 标准 | Standard | `standard` | 128kbps |
| 较高 | Higher | `higher` | API 额外档位，通常192kbps |
| 极高 | HQ | `exhigh` | 320kbps |
| 无损 | SQ | `lossless` | 44.1–48kHz / 16bit / 2声道 |
| 高解析度无损 | Hi-Res | `hires` | 48–192kHz / 24bit / 2声道 |
| 高清臻音 | Spatial Audio | `jyeffect` | 96kHz / 24bit / 2声道 |
| 杜比全景声 | Dolby Atmos | `dolby` | 48kHz / 位深未注明 / 最高7.1.4声道 |
| 臻音全景声 | Audio Vivid | `vivid` | 44.1kHz / 16bit / 最高7.1.4声道 |
| 超清母带 | Master | `jymaster` | 192kHz / 24bit / 2声道 |
| 沉浸环绕声 | Surround Audio | `sky` | 44.1kHz / 16bit / 5.1或2声道 |

以上规格根据使用者提供的客户端规格表整理，仅为档位参考，不是对每首歌的实测值或保证。`kbps` 是码率，不是采样频率；实际采样率、位深、声道和可用音质以接口返回的音源、歌曲版权及账号权限为准。QQ 等平台发送语音时可能再次转码，选择高规格源文件不代表最终语音保留该规格。

普通音质按 `hires → lossless → exhigh → higher → standard` 向下降级，从所选档位开始，不反向升级。特殊声效/环绕格式不视为严格的高低顺序：先请求所选格式，不可用时再尝试上述普通音质序列。空音源及不支持/无权限的 400、403、404 响应可继续降级；服务器错误不会被静默吞掉。

播放信息使用「优先音质」标注配置值，不将偏好设置误称为接口实际返回的音质。

## 📝 使用方法

- **命令点歌**：
  ```
  /点歌 歌曲名
  ```
  (别名: `/music`, `/听歌`, `/网易云`)

- **自然语言点歌**：
  ```
  来一首 晴天
  播放 稻香
  听听 七里香
  ```

- **选择歌曲**：
  在机器人返回搜索列表后，直接回复您想听的歌曲对应的**数字**即可。

## 💖 致谢

感谢 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 提供了如此强大的机器人框架。

---
*Made with ❤️ by NachoCrazy*
