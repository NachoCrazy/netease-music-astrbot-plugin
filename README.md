# AstrBot 豪华网易云点歌插件

[![version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/NachoCrazy/netease-music-astrbot-plugin)
[![license](https://img.shields.io/github/license/NachoCrazy/netease-music-astrbot-plugin.svg)](LICENSE)

这是一款为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的，功能强大且体验豪华的网易云音乐点歌插件。

## ✨ 功能亮点

- **交互式点歌**：通过关键词搜索歌曲，机器人会返回一个列表供您选择。
- **豪华信息卡片**：播放时，会发送包含**歌曲封面**、**详细信息**（歌名、歌手、专辑、时长）的精美图文卡片。
- **语音播放**：直接发送可播放的语音消息，在聊天窗口即可享受音乐。
- **音质自动回退**：优先请求您设定的音质，不可用时自动降级重试（依次尝试 `quality` 配置值、`exhigh`、`higher`、`standard`），尽量提高播放成功率。
- **拿不到就不播放**：官方接口没有返回可播放地址时（例如未配置 Cookie 的会员曲、无版权歌曲），插件会直接提示原因，而不会发送无法播放的音频。
- **多种触发方式**：支持命令（如 `/点歌`）和自然语言（如 `来一首...`）两种方式点歌。
- **WebUI配置**：可在 AstrBot 的网页后台轻松配置各项参数。

## ⚙️ 安装与配置

### 依赖

本插件依赖一个外部的 **Netease Cloud Music API (增强版)** 服务。请您务必先根据其文档自行部署该服务。

- **API 仓库地址**: [https://github.com/neteasecloudmusicapienhanced/api-enhanced](https://github.com/neteasecloudmusicapienhanced/api-enhanced)

推荐的部署方式是使用 Docker。

### 安装

1. 在 AstrBot 的插件商店中搜索 `astrbot_plugin_netease_music` 并安装。
2. 或者，直接将本项目克隆到您的 AstrBot `data/plugins` 目录下。

### 配置

安装并重启 AstrBot 后，在网页后台的 **插件配置** -> **`astrbot_plugin_netease_music`** 中进行设置：

1. **网易云 API 地址**（`api_url`）：填写您部署的 API 服务的地址，例如 `http://127.0.0.1:3000`（这也是默认值）。
2. **优先音质**（`quality`）：可选 `lossless` / `exhigh` / `higher` / `standard`，默认 `exhigh`；该档位不可用时插件会自动尝试更低音质。
3. **搜索结果数量**（`search_limit`）：每次搜索展示给用户的歌曲选项数量，默认 `5`。
4. **网易云 Cookie**（`cookie`）：可选。填写登录后的 Cookie 后可播放 VIP 歌曲。

当前版本在配置面板中**只有以上 4 项**，没有其他开关。

## 🧪 测试

本仓库暂无自动化测试。合并前的验证方式是手动冒烟：在 AstrBot 中加载插件，确认 `/点歌 歌曲名` 能返回歌曲列表、回复数字能正常播放，并留意日志中的 API 连接与 ffmpeg 告警。

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
  在机器人返回搜索列表后，直接回复您想听的歌曲对应的**数字**即可。搜索结果的有效期为 **60 秒**，超时后需要重新点歌。

## 💖 致谢

感谢 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 提供了如此强大的机器人框架。

---
*Made with ❤️ by NachoCrazy*
