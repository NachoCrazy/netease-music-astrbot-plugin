# 网易云音乐点歌插件 (Netease Music Enhanced Plugin)

适用于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的网易云音乐点歌插件，支持通过命令或自然语言点播网易云音乐歌曲。

> ⚠️ **重要提示**: 本插件需要依赖 [NeteaseCloudMusicApiEnhanced](https://github.com/neteasecloudmusicapienhanced/api-enhanced) 服务才能正常工作，请务必先部署该服务.

## 功能特性

- 🎵 通过命令或自然语言触发点歌功能
- 🔍 搜索网易云音乐曲库，展示详细歌曲信息
- 📷 显示专辑封面和歌曲详细信息
- 🎧 支持高质量音频播放（exhigh级别）
- 🗣️ 以语音消息形式发送歌曲
- ⌨️ 数字快捷选择想听的歌曲

## 安装方式

### 方法一：通过 AstrBot 管理面板安装（推荐）
1. 进入 AstrBot 管理面板
2. 进入插件市场
3. 搜索 "网易云音乐"
4. 点击安装

### 方法二：手动安装
1. 下载本仓库的最新 release
2. 解压后将文件夹放入 AstrBot 的 `data/plugins/` 目录
3. 重启 AstrBot

### 方法三：通过Astrbot后台安装
在 AstrBot 中的后台直接复制该git去导入：

## 使用说明

### 触发方式
1. 命令触发：
   ```
   /点歌 歌名
   ```
   或使用别名：`/music`、`/听歌`、`/网易云`

2. 自然语言触发：
   - 来一首只因你太美
   - 播放青花瓷
   - 听听稻香
   - 点歌夜曲

### 选择歌曲
搜索结果会显示前5首歌曲，回复相应数字（1-5）即可选择播放。

## 配置要求

需要配合 [NeteaseCloudMusicApiEnhanced](https://github.com/neteasecloudmusicapienhanced/api-enhanced) 使用：

1. 部署 NeteaseCloudMusicApiEnhanced 服务
2. 在插件配置中填写 API 地址（默认为 http://127.0.0.1:3000）

## 配置说明

安装插件后，在 AstrBot 管理面板的插件配置页面可以进行以下配置：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enabled | 是否启用插件 | true |
| api_url | NeteaseCloudMusicApi 地址 | http://127.0.0.1:3000 |

## 开源协议

MIT License

## 作者

[NachoCrazy](https://github.com/NachoCrazy)
