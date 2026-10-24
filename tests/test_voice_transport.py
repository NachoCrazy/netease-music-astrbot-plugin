"""Run with python -m unittest discover -s tests -v; no bot connection needed."""
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


def load_plugin():
    # Isolate AstrBot's runtime so tests never start a client or send a message.
    api = ModuleType("astrbot.api")
    api.star = SimpleNamespace(Star=object)
    api.logger = Mock()
    events = ModuleType("astrbot.api.event")
    events.AstrMessageEvent = object
    decorator = lambda *args, **kwargs: lambda handler: handler
    events.filter = SimpleNamespace(command=decorator, regex=decorator)
    components = ModuleType("astrbot.api.message_components")
    components.Plain = lambda text: ("plain", text)
    components.Image = SimpleNamespace(fromBase64=lambda data: ("image", data))
    components.Record = Mock(side_effect=lambda **kwargs: ("record", kwargs))
    chains = ModuleType("astrbot.core.message.message_event_result")
    chains.MessageChain = list
    modules = {
        "aiohttp": Mock(),
        "astrbot": ModuleType("astrbot"),
        "astrbot.api": api,
        "astrbot.api.event": events,
        "astrbot.api.message_components": components,
        "astrbot.core": ModuleType("astrbot.core"),
        "astrbot.core.message": ModuleType("astrbot.core.message"),
        "astrbot.core.message.message_event_result": chains,
    }
    spec = importlib.util.spec_from_file_location(
        "netease_plugin_under_test", Path(__file__).resolve().parents[1] / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", modules):
        spec.loader.exec_module(module)
    return module


plugin = load_plugin()
AUDIO_URL = "https://audio.example.invalid/song.mp3?signature=keep-this"


class VoiceTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = plugin.Main.__new__(plugin.Main)
        self.main.config = {"quality": "exhigh"}
        self.main.api = SimpleNamespace(download_image=AsyncMock(return_value=b"cover"))
        self.bot = SimpleNamespace(send_group_msg=AsyncMock(), send_private_msg=AsyncMock())
        self.event = SimpleNamespace(
            bot=self.bot,
            send=AsyncMock(),
            get_platform_name=lambda: "aiocqhttp",
            get_self_id=lambda: "10001",
            is_private_chat=lambda: False,
            get_group_id=lambda: "20002",
            get_sender_id=lambda: "30003",
        )
        plugin.Record.reset_mock()

    async def send_song(self):
        await self.main._send_song_messages(
            self.event, 1, "Title", "Artist", "Album", "4:39", "https://cover.example.invalid", AUDIO_URL
        )

    def expected_message(self):
        return [{"type": "record", "data": {"file": AUDIO_URL}}]

    async def test_group_sends_url_without_constructing_record(self):
        await self.send_song()
        self.bot.send_group_msg.assert_awaited_once_with(
            group_id=20002, message=self.expected_message(), self_id="10001"
        )
        self.bot.send_private_msg.assert_not_awaited()
        plugin.Record.assert_not_called()
        self.event.send.assert_awaited_once()
        self.assertEqual(self.event.send.call_args.args[0][-1][0], "image")

    async def test_private_sends_url_to_sender(self):
        self.event.is_private_chat = lambda: True
        await self.send_song()
        self.bot.send_private_msg.assert_awaited_once_with(
            user_id=30003, message=self.expected_message(), self_id="10001"
        )
        self.bot.send_group_msg.assert_not_awaited()

    async def test_missing_self_id_uses_default_connection(self):
        self.event.get_self_id = lambda: ""
        await self.send_song()
        self.bot.send_group_msg.assert_awaited_once_with(group_id=20002, message=self.expected_message())

    async def test_other_platform_keeps_record_transport(self):
        self.event.get_platform_name = lambda: "other"
        await self.send_song()
        plugin.Record.assert_called_once_with(file=AUDIO_URL)
        self.assertEqual(self.event.send.await_count, 2)
        self.bot.send_group_msg.assert_not_awaited()
        self.bot.send_private_msg.assert_not_awaited()

    async def test_record_ffmpeg_error_keeps_link_fallback(self):
        self.event.get_platform_name = lambda: "other"
        self.event.send.side_effect = [None, RuntimeError("ffmpeg unavailable"), None]
        await self.send_song()
        self.assertEqual(self.event.send.await_count, 3)
        self.assertIn(AUDIO_URL, self.event.send.call_args.args[0][0][1])

    async def test_onebot_timeout_propagates_without_duplicate_retry(self):
        self.bot.send_group_msg.side_effect = RuntimeError("WebSocket API call timeout")
        with self.assertRaisesRegex(RuntimeError, "WebSocket API call timeout"):
            await self.send_song()
        self.bot.send_group_msg.assert_awaited_once()
        self.event.send.assert_awaited_once()
        plugin.Record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
