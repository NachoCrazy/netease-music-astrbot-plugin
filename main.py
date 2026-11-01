"""
Netease Music Enhanced Plugin for AstrBot
- Author: NachoCrazy
- Repo: https://github.com/NachoCrazy/netease-music-astrbot-plugin
- Features: Interactive song selection, cover display, audio playback, and auto quality fallback.
"""

import os
import re
import time
import base64
import aiohttp
import asyncio
import shutil
import subprocess
import urllib.parse
from typing import Dict, Any, Optional, List, NamedTuple

from astrbot.api import star, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.message_components import Plain, Image, Record


# --- 音源结果 ---
class AudioResult(NamedTuple):
    """音源探测结果。只有 status == "ok" 时 url 才非空，试听片段永远不会从这里流出。"""

    url: Optional[str]
    status: str
    info: Dict[str, Any]


def _as_int(value: Any, default: int = 0) -> int:
    """把接口里的数字字段（int / float / 数字字符串）统一成 int，非法值给 default。"""
    if isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _err_brief(exc: BaseException) -> str:
    """异常摘要：只给类型与 HTTP 状态码，绝不带 URL。

    请求 URL 里带 cookie（&cookie=MUSIC_U=...），而 aiohttp 的
    ClientResponseError.__str__ 会带上完整 URL，直接打日志等于泄露用户凭据。
    """
    status = getattr(exc, "status", None)
    return f"{type(exc).__name__}({status})" if status else type(exc).__name__


def _is_trial(info: Dict[str, Any]) -> bool:
    """freeTrialInfo 是"非空且不为字符串 null"时才视为试听片段。

    空对象 {} / 空数组 [] / None / "null" 都表示可放整首，不能判成试听。
    """
    value = info.get("freeTrialInfo")
    return bool(value) and value != "null"


def _is_truncated(info: Dict[str, Any], duration_ms: int) -> bool:
    """兜底：响应带 time 且明显短于 dt（容差 max(2s, 2%)）即为残片/试听。

    服务端试听长度会在 45s/30s 之间漂移，也可能返回 freeTrialInfo 为空的残片，
    所以即便 freeTrialInfo 为空，也不能只凭它判定为整首。
    """
    info_time = _as_int(info.get("time"))
    duration_ms = _as_int(duration_ms)
    if not duration_ms or not info_time:
        return False
    return info_time < duration_ms - max(2000, duration_ms * 0.02)


# --- Helpers ---
def _find_ffmpeg() -> Optional[str]:
    """
    Try to locate the ffmpeg executable.
    Returns the absolute path or None.
    """
    # 1. Standard PATH lookup
    path = shutil.which("ffmpeg")
    if path:
        return path

    # 2. Common Windows install locations
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        r"C:\Users\Administrator\ffmpeg\bin\ffmpeg.exe",
        r"C:\Windows\ffmpeg\bin\ffmpeg.exe",
    ]
    # Also try the current working directory / project root
    candidates.append(os.path.join(os.getcwd(), "ffmpeg", "bin", "ffmpeg.exe"))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    # 3. Fallback: try subprocess to resolve via the shell
    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        if proc.returncode == 0:
            # It worked; the binary is somewhere in the system PATH
            # but not visible to shutil.which in this context.
            # Return "ffmpeg" so that subsequent subprocess calls still work
            return "ffmpeg"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


# --- API Wrapper ---
class NeteaseMusicAPI:
    """
    A wrapper for the NeteaseCloudMusicApi to simplify interactions.
    Encapsulates API calls for searching, getting details, and fetching audio URLs.
    """
    def __init__(self, api_url: str, session: aiohttp.ClientSession):
        self.base_url = api_url.rstrip("/")
        self.session = session

    async def search_songs(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        """Search for songs by keyword."""
        url = f"{self.base_url}/search?keywords={urllib.parse.quote(keyword)}&limit={limit}&type=1"
        async with self.session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
            return data.get("result", {}).get("songs", [])

    async def get_song_details(self, song_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information for a single song."""
        url = f"{self.base_url}/song/detail?ids={str(song_id)}"
        async with self.session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
            return data["songs"][0] if data.get("songs") else None

    def _audio_result(self, song_id: int, status: str, info: Optional[Dict[str, Any]], src: str) -> AudioResult:
        """统一收口：只有 status == "ok" 才带 url，其余一律 url=None。"""
        info = info or {}
        url = info.get("url") if status == "ok" else None
        logger.info(
            "[get_audio_url] song=%s status=%s level=%s type=%s time=%s freeTrial=%s src=%s",
            song_id, status, info.get("level"), info.get("type"),
            info.get("time"), info.get("freeTrialInfo"), src,
        )
        return AudioResult(url=url, status=status, info=info)

    async def get_audio_url(self, song_id: int, quality: str, cookie: str = "",
                            duration_ms: int = 0) -> AudioResult:
        """
        获取播放 URL：按音质从高到低探测，返回结构化结果。

        返回 AudioResult(url, status, info)，status 取值：
        ok / trial_only / paid_album / no_copyright / upstream_error / unavailable。
        试听片段与残片只做记录，绝不作为结果返回。
        """
        qualities_to_try = list(dict.fromkeys([quality, "exhigh", "higher", "standard"]))
        trial_info: Dict[str, Any] = {}
        last_info: Dict[str, Any] = {}
        got_response = False
        no_resource = False
        paid_album = False
        duration_ms = _as_int(duration_ms)

        for q in qualities_to_try:
            # 在 URL 中拼接 cookie
            url = f"{self.base_url}/song/url/v1?id={str(song_id)}&level={q}&cookie={cookie}"
            try:
                async with self.session.get(url) as r:
                    r.raise_for_status()
                    info = ((await r.json()).get("data") or [{}])[0] or {}
            except Exception as e:  # 单档失败不影响其它档
                # 只记类型/状态码：异常字符串里可能带完整 URL（含 cookie）
                logger.warning("[get_audio_url] official level=%s failed: %s", q, _err_brief(e))
                continue
            got_response = True
            last_info = info
            if not info.get("url"):
                if info.get("fee") == 4:
                    paid_album = True
                elif info.get("code") == 404:
                    no_resource = True
                continue
            if _is_trial(info) or _is_truncated(info, duration_ms):
                trial_info = trial_info or info
                continue
            return self._audio_result(song_id, "ok", info, f"official:{q}")

        if trial_info:
            return self._audio_result(song_id, "trial_only", trial_info, "none")
        if no_resource:
            return self._audio_result(song_id, "no_copyright", last_info, "none")
        if paid_album:
            return self._audio_result(song_id, "paid_album", last_info, "none")
        if not got_response:
            return self._audio_result(song_id, "upstream_error", {}, "none")
        # 接口能正常响应，但所有档位都没有可播地址
        return self._audio_result(song_id, "unavailable", last_info, "none")

    async def download_image(self, url: str) -> Optional[bytes]:
        """Download image data from a URL."""
        if not url:
            return None
        async with self.session.get(url) as r:
            if r.status == 200:
                return await r.read()
        return None


# --- Main Plugin Class ---
class Main(star.Star):
    """
    A cat-maid themed Netease Music plugin that allows users to search for,
    select, and play songs directly in the chat.
    """
    def __init__(self, context, config: Optional[Dict[str, Any]] = None):
        super().__init__(context)
        self.config = config or {}
        self.config.setdefault("api_url", "http://127.0.0.1:3000")
        self.config.setdefault("quality", "exhigh")
        self.config.setdefault("search_limit", 5)
        # 仅新增这一行配置初始化
        self.config.setdefault("cookie", "")
        
        self.waiting_users: Dict[str, Dict[str, Any]] = {}
        self.song_cache: Dict[str, List[Dict[str, Any]]] = {}
        
        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        self.api = NeteaseMusicAPI(self.config["api_url"], self.http_session)
        
        # Ensure ffmpeg is discoverable for Record components
        self._ffmpeg_path = _find_ffmpeg()
        if self._ffmpeg_path:
            ffmpeg_dir = os.path.dirname(self._ffmpeg_path)
            current_path = os.environ.get("PATH", "")
            if ffmpeg_dir not in current_path:
                os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path
                logger.info(f"Netease Music plugin: Added ffmpeg directory to PATH: {ffmpeg_dir}")
        else:
            logger.warning("Netease Music plugin: ffmpeg not found in PATH. Record (voice) may fail.")
        
        self.cleanup_task: Optional[asyncio.Task] = None

    # --- Lifecycle Hooks ---

    async def initialize(self):
        """Starts the background cleanup task when the plugin is activated."""
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("Netease Music plugin: Background cleanup task started.")

    async def terminate(self):
        """Cleans up resources when the plugin is unloaded."""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                logger.info("Netease Music plugin: Background cleanup task cancelled.")
        
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            logger.info("Netease Music plugin: HTTP session closed.")

    async def _periodic_cleanup(self):
        """A background task that runs periodically to clean up expired sessions."""
        while True:
            await asyncio.sleep(60)  # Run every 60 seconds
            now = time.time()
            expired_sessions = []
            
            for session_id, user_session in self.waiting_users.items():
                if user_session['expire'] < now:
                    expired_sessions.append((session_id, user_session['key']))
            
            if expired_sessions:
                logger.info(f"Netease Music plugin: Cleaning up {len(expired_sessions)} expired session(s).")
                for session_id, cache_key in expired_sessions:
                    if session_id in self.waiting_users:
                        del self.waiting_users[session_id]
                    if cache_key in self.song_cache:
                        del self.song_cache[cache_key]

    # --- Event Handlers ---

    @filter.command("点歌", alias={"music", "听歌", "网易云"})
    async def cmd_handler(self, event: AstrMessageEvent, keyword: str = ""):
        """Handles the '/点歌' command."""
        if not keyword.strip():
            await event.send(MessageChain([Plain("主人，请告诉我您想听什么歌喵~ 例如：/点歌 Lemon")]))
            return
        await self.search_and_show(event, keyword.strip())

    @filter.regex(r"(?i)^(来.?一首|播放|听.?听|点歌|唱.?一首|来.?首)\s*([^\s].+?)(的歌|的歌曲|的音乐|歌|曲)?$")
    async def natural_language_handler(self, event: AstrMessageEvent):
        """Handles song requests in natural language."""
        match = re.search(r"(?i)^(来.?一首|播放|听.?听|点歌|唱.?一首|来.?首)\s*([^\s].+?)(的歌|的歌曲|的音乐|歌|曲)?$", event.message_str)
        if match:
            keyword = match.group(2).strip()
            if keyword:
                event.stop_event()
                await self.search_and_show(event, keyword)

    @filter.regex(r"^\d+$", priority=999)
    async def number_selection_handler(self, event: AstrMessageEvent):
        """Handles user's numeric choice from the search results."""
        session_id = event.get_session_id()
        if session_id not in self.waiting_users:
            return

        user_session = self.waiting_users[session_id]
        if time.time() > user_session["expire"]:
            # Let the periodic cleanup handle the removal
            return

        try:
            num = int(event.message_str.strip())
        except ValueError:
            return

        limit = self.config.get("search_limit", 5)
        if not (1 <= num <= limit):
            return

        event.stop_event()

        # Fix: 先清掉 waiting_users，防止平台重试/重复事件导致重复发消息
        del self.waiting_users[session_id]

        await self.play_selected_song(event, user_session["key"], num)

    # --- Core Logic ---

    async def search_and_show(self, event: AstrMessageEvent, keyword: str):
        """Searches for songs and displays the results to the user."""
        try:
            songs = await self.api.search_songs(keyword, self.config["search_limit"])
        except Exception as e:
            logger.error(f"Netease Music plugin: API search failed. Error: {e!s}")
            await event.send(MessageChain([Plain(f"呜喵...和音乐服务器的连接断掉了...主人，请检查一下API服务是否正常运行喵？")]))
            return

        if not songs:
            await event.send(MessageChain([Plain(f"对不起主人...我...我没能找到「{keyword}」这首歌喵... T_T")]))
            return

        cache_key = f"{event.get_session_id()}_{int(time.time())}"
        self.song_cache[cache_key] = songs

        response_lines = [f"主人，我为您找到了 {len(songs)} 首歌曲喵！请回复数字告诉我您想听哪一首~"]
        for i, song in enumerate(songs, 1):
            artists = " / ".join(a["name"] for a in song.get("artists", []))
            album = song.get("album", {}).get("name", "未知专辑")
            duration_ms = song.get("duration", 0)
            dur_str = f"{duration_ms//60000}:{(duration_ms%60000)//1000:02d}"
            response_lines.append(f"{i}. {song['name']} - {artists} 《{album}》 [{dur_str}]")

        await event.send(MessageChain([Plain("\n".join(response_lines))]))

        self.waiting_users[event.get_session_id()] = {"key": cache_key, "expire": time.time() + 60}

    @staticmethod
    def _audio_fail_text(status: str) -> str:
        """按取流状态给失败文案，不再把"会员/没版权/连不上"混成一句。"""
        if status == "no_copyright":
            return "呜喵……这首歌没有版权，放不了喵。"
        if status == "paid_album":
            return "呜喵……这张是付费数字专辑，主人买下来才能听喵。"
        if status == "upstream_error":
            return "呜喵……和音乐服务器的连接断掉了，连不上点歌服务喵。"
        if status == "unavailable":
            return "呜喵……这首歌暂时没有可用的音源，放不了喵。"
        return "呜喵……这首歌是会员曲，只能听到试听片段，没办法完整放给主人喵。"

    async def play_selected_song(self, event: AstrMessageEvent, cache_key: str, num: int) -> str:
        """Plays the song selected by the user. 返回 "ok" 或失败状态名。"""
        if cache_key not in self.song_cache:
            await event.send(MessageChain([Plain("喵呜~ 主人选择得太久了，搜索结果已经凉掉了哦，请重新点歌吧~")]))
            return "expired"

        songs = self.song_cache[cache_key]
        if not (1 <= num <= len(songs)):
             await event.send(MessageChain([Plain("主人，您输入的数字不对哦，请选择列表里的歌曲编号喵~")]))
             return "bad_index"
             
        selected_song = songs[num - 1]
        song_id = selected_song["id"]
        
        try:
            song_details = await self.api.get_song_details(song_id)
            if not song_details:
                raise ValueError("无法获取歌曲详细信息。")

            # 传入配置中的 cookie 与歌曲真实时长（dt），用于识别试听/残片
            audio = await self.api.get_audio_url(
                song_id,
                self.config["quality"],
                self.config.get("cookie", ""),
                song_details.get("dt", 0),
            )
            if audio.status != "ok" or not audio.url:
                # 试听片段绝不发送：只按状态给文案
                logger.info(f"[play_selected_song] song={song_id} 未放出: status={audio.status}")
                await event.send(MessageChain([Plain(self._audio_fail_text(audio.status))]))
                return audio.status

            title = song_details.get("name", "")
            artists = " / ".join(a["name"] for a in song_details.get("ar", []))
            album = song_details.get("al", {}).get("name", "未知专辑")
            cover_url = song_details.get("al", {}).get("picUrl", "")
            duration_ms = song_details.get("dt", 0)
            dur_str = f"{duration_ms//60000}:{(duration_ms%60000)//1000:02d}"

            await self._send_song_messages(event, num, title, artists, album, dur_str, cover_url, audio.url, audio.info)
            return "ok"

        except Exception as e:
            logger.error(f"Netease Music plugin: Failed to play song {song_id}. Error: {e!s}")
            await event.send(MessageChain([Plain(f"呜...获取歌曲信息的时候失败了喵...")]))
            return "detail_failed"
        finally:
            if cache_key in self.song_cache:
                del self.song_cache[cache_key]

    def _format_quality(self, info: Optional[Dict[str, Any]]) -> str:
        """卡片音质：显示实际拿到的 level / 格式 / 码率，字段缺失才退回配置值并标注。"""
        info = info or {}
        level = info.get("level") or ""
        fmt = info.get("type") or ""
        br = _as_int(info.get("br"))
        detail = " ".join(x for x in (fmt, f"{br // 1000}k" if br else "") if x)
        if level:
            return f"{level} / {detail}" if detail else str(level)
        cfg = self.config.get("quality", "")
        return f"{cfg} (配置)" if cfg else "未知"

    async def _send_song_messages(self, event: AstrMessageEvent, num: int, title: str, artists: str, album: str, dur_str: str, cover_url: str, audio_url: str, audio_info: Optional[Dict[str, Any]] = None):
        """Constructs and sends the song info and audio messages."""
        detail_text = f"""遵命，主人！为您播放第 {num} 首歌曲~

♪ 歌名：{title}
🎤 歌手：{artists}
💿 专辑：{album}
⏳ 时长：{dur_str}
✨ 音质：{self._format_quality(audio_info)}

请主人享用喵~
"""
        info_components = [Plain(detail_text)]

        image_data = await self.api.download_image(cover_url)
        if image_data:
            info_components.append(Image.fromBase64(base64.b64encode(image_data).decode()))

        await event.send(MessageChain(info_components))
        
        # Try to send as a voice message (Record component)
        try:
            await event.send(MessageChain([Record(file=audio_url)]))
        except Exception as e:
            err_msg = str(e)
            if "ffmpeg" in err_msg.lower() or "not found" in err_msg.lower():
                # Fallback if ffmpeg is still unavailable after PATH fix attempt
                logger.warning(f"Netease Music plugin: Record(voice) failed, falling back to link. Error: {err_msg}")
                await event.send(MessageChain([Plain(f"🔊 点击播放：{audio_url}")]))
            else:
                raise
