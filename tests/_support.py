"""测试支撑：用最小 stub 顶掉 astrbot，再加载仓库根目录的 main.py。

用例全部离线运行：不启动 AstrBot、不访问网络，也不新增任何测试依赖。
"""

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True


def _register(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


class CapturedLog:
    """替身 logger：把日志留在内存里，便于断言。"""

    def __init__(self) -> None:
        self.records = []

    def _add(self, level: str, msg, args) -> None:
        try:
            text = msg % args if args else msg
        except Exception:  # 日志格式串写错不应该让测试炸掉
            text = f"{msg} {args}"
        self.records.append((level, text))

    def info(self, msg, *args):
        self._add("INFO", msg, args)

    def warning(self, msg, *args):
        self._add("WARN", msg, args)

    def error(self, msg, *args):
        self._add("ERROR", msg, args)

    def debug(self, msg, *args):
        self._add("DEBUG", msg, args)


LOG = CapturedLog()


def install_astrbot_stubs() -> None:
    """注册 astrbot 的最小可用替身；重复调用无副作用。"""
    if getattr(sys.modules.get("astrbot"), "_is_test_stub", False):
        return

    astrbot = _register("astrbot")
    astrbot._is_test_stub = True
    api = _register("astrbot.api")
    core = _register("astrbot.core")
    core_message = _register("astrbot.core.message")
    message_event_result = _register("astrbot.core.message.message_event_result")
    api_event = _register("astrbot.api.event")
    message_components = _register("astrbot.api.message_components")

    astrbot.api = api
    astrbot.core = core
    core.message = core_message

    class Star:
        def __init__(self, context=None):
            self.context = context

    api.star = types.SimpleNamespace(Star=Star)
    api.logger = LOG

    def _decorator(*args, **kwargs):
        def wrap(func):
            return func

        return wrap

    api_event.AstrMessageEvent = object
    api_event.filter = types.SimpleNamespace(
        command=_decorator, regex=_decorator, llm_tool=_decorator
    )

    class MessageChain:
        def __init__(self, components=None):
            self.components = list(components or [])

    class Plain:
        def __init__(self, text=""):
            self.text = text

    class Image:
        @classmethod
        def fromBase64(cls, data):
            return cls()

    class Record:
        def __init__(self, file="", **kwargs):
            self.file = file

    message_event_result.MessageChain = MessageChain
    message_components.Plain = Plain
    message_components.Image = Image
    message_components.Record = Record


def load_plugin():
    """加载仓库根目录的 main.py，返回模块对象。"""
    install_astrbot_stubs()
    name = "netease_music_plugin_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class MockResponse:
    """aiohttp 响应的最小替身。"""

    def __init__(self, payload, status: int = 200):
        self._payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._payload

    async def read(self):
        return b""


class MockSession:
    """按 URL 路由预设响应的会话替身，并记录每次请求拿到的 timeout。"""

    def __init__(self, official=None, unblock=None, detail=None, search=None, image=None):
        self.official = official
        self.unblock = unblock
        self.detail = detail
        self.search = search
        self.image = image
        self.calls = []

    def _route(self, url):
        if "unblock=true" in url:
            return self.unblock
        if "/song/detail" in url:
            return self.detail
        if "/search" in url:
            return self.search
        if not url.startswith("http://api.test"):
            return self.image
        return self.official

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs.get("timeout")))
        payload = self._route(url)
        if isinstance(payload, BaseException):
            raise payload
        if callable(payload):
            payload = payload(url)
        return MockResponse(payload if payload is not None else {})


class FakeEvent:
    """只实现 send 的事件替身，记录发出去的每一条 MessageChain。"""

    def __init__(self):
        self.sent = []

    async def send(self, chain):
        self.sent.append(chain)

    def get_session_id(self):
        return "test:session"

    @property
    def components(self):
        return [c for chain in self.sent for c in chain.components]

    def texts(self):
        return [c.text for c in self.components if hasattr(c, "text")]

    def records(self):
        return [c for c in self.components if type(c).__name__ == "Record"]


def song_url_payload(url=None, time=0, free_trial=None, level="exhigh", code=200, **extra):
    """构造 /song/url/v1 的 data[0] 响应。"""
    info = {
        "url": url,
        "time": time,
        "freeTrialInfo": free_trial,
        "level": level,
        "code": code,
    }
    info.update(extra)
    return {"data": [info]}
