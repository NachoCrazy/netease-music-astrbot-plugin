# Netease Music Enhanced Plugin for AstrBot
# Author: NachoCrazy
# Description: 豪华网易云点歌：封面+详情+无损语音

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.message_components import Plain, Image, Record
import re
import aiohttp
import urllib.parse
import time

class Main(star.Star):
    def __init__(self, context, config=None):
        super().__init__(context)
        self.config = {"enabled": True, "api_url": "http://127.0.0.1:3000"} if config is None else config
        self.waiting_users = {}      # {session_id: {"key": cache_key, "expire": time}}
        self.song_cache = {}         # {cache_key: songs}
        # 全局复用 Session，永不关闭（除非插件卸载）
        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))

    @filter.command("点歌", alias={"music", "听歌", "网易云"})
    async def cmd(self, event: AstrMessageEvent, keyword: str = ""):
        if not keyword.strip():
            await event.send(MessageChain([Plain("用法：/点歌 歌名\n或说：来一首只因你太美")]))
            return
        await self.search_and_show(event, keyword.strip())

    @filter.regex(r"(?i)(来.?一首|播放|听.?听|点歌|唱.?一首|来.?首)\s*([^\s].+?)(的歌|的歌曲|的音乐|歌|曲)?\s*$")
    async def natural(self, event: AstrMessageEvent):
        m = re.search(r"(?i)(来.?一首|播放|听.?听|点歌|唱.?一首|来.?首)\s*([^\s].+?)(的歌|的歌曲|的音乐|歌|曲)?\s*$", event.message_str)
        if m:
            await self.search_and_show(event, m.group(2).strip())

    # 最高优先级捕获纯数字回复
    @filter.regex(r"^\d+$", priority=999)
    async def catch_number(self, event: AstrMessageEvent):
        sid = event.get_session_id()
        if sid not in self.waiting_users:
            return

        info = self.waiting_users[sid]
        if time.time() > info["expire"]:
            del self.waiting_users[sid]
            return

        num = int(event.message_str.strip())
        if not (1 <= num <= 5):
            return

        event.stop_event()  # 拦截，不让AI或其他插件处理
        await self.play_selected(event, info["key"], num)
        del self.waiting_users[sid]

    async def search_and_show(self, event: AstrMessageEvent, keyword: str):
        if not self.config.get("enabled", True):
            return

        base = self.config.get("api_url", "http://127.0.0.1:3000").rstrip("/")
        try:
            r = await self.http_session.get(f"{base}/search?keywords={urllib.parse.quote(keyword)}&limit=5&type=1")
            data = await r.json()
        except Exception as e:
            await event.send(MessageChain([Plain("网易云API连接失败，请检查是否启动")]))
            return

        songs = data.get("result", {}).get("songs", [])
        if not songs:
            await event.send(MessageChain([Plain(f"没搜到「{keyword}」")]))
            return

        cache_key = f"{event.get_session_id()}_{int(time.time())}"
        self.song_cache[cache_key] = songs

        lines = [f"找到 {len(songs)} 首歌，回复数字点歌："]
        for i, s in enumerate(songs, 1):
            ar = " / ".join(a["name"] for a in s["artists"])
            al = s.get("album", {}).get("name", "未知专辑")
            dur = f"{s['duration']//60000}:{(s['duration']%60000)//1000:02d}"
            lines.append(f"{i}. {s['name']} - {ar} 《{al}》 [{dur}]")

        await event.send(MessageChain([Plain("\n".join(lines))]))

        self.waiting_users[event.get_session_id()] = {"key": cache_key, "expire": time.time() + 60}

    async def play_selected(self, event: AstrMessageEvent, cache_key: str, num: int):
        if cache_key not in self.song_cache:
            await event.send(MessageChain([Plain("搜索结果已过期，请重新点歌")]))
            return

        song = self.song_cache[cache_key][num-1]
        title = song["name"]
        artist = " / ".join(a["name"] for a in song["artists"])
        album = song.get("album", {}).get("name", "未知专辑")
        cover = song.get("album", {}).get("picUrl", "")
        dur = f"{song['duration']//60000}:{(song['duration']%60000)//1000:02d}"

        base = self.config.get("api_url", "http://127.0.0.1:3000").rstrip("/")
        try:
            r = await self.http_session.get(f"{base}/song/url/v1?id={song['id']}&level=exhigh")
            data = await r.json()
            audio_url = data.get("data", [{}])[0].get("url")
        except Exception as e:
            await event.send(MessageChain([Plain(f"获取音频失败：{str(e)}")]))
            return

        if not audio_url:
            await event.send(MessageChain([Plain("这首歌暂时无法播放（可能需要登录或会员）")]))
            return

        detail = f"""已播放第 {num} 首

标题：{title}
歌手：{artist}
专辑：{album}
时长：{dur}

无损播放中"""

        components = [Plain(detail)]
        if cover:
            components.append(Image(url=cover))
        components.append(Record(file=audio_url))

        await event.send(MessageChain(components))
        del self.song_cache[cache_key]

    async def terminate(self):
        if not self.http_session.closed:
            await self.http_session.close()