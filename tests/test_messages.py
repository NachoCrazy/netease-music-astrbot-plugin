"""PR1-1 回归：失败文案分档 + 卡片音质如实展示；成功路径仍走 event.send + Record。"""

import asyncio
import unittest

from _support import FakeEvent, MockSession, load_plugin, song_url_payload

plugin = load_plugin()

MEMBER_ID = 1869929814
MEMBER_DT = 255582
FREE_ID = 450048197
FREE_DT = 1083141

DETAIL_PAYLOAD = {
    "songs": [
        {
            "id": FREE_ID,
            "name": "生命線",
            "ar": [{"name": "テスト"}],
            "al": {"name": "アルバム", "picUrl": ""},
            "dt": MEMBER_DT,
        }
    ]
}


class FailTextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.main = plugin.Main(context=None, config={"api_url": "http://api.test"})

    async def asyncTearDown(self):
        await self.main.http_session.close()

    def test_every_status_has_its_own_text(self):
        statuses = ["trial_only", "unblock_failed", "paid_album", "no_copyright", "upstream_error"]
        texts = [self.main._audio_fail_text(status) for status in statuses]
        self.assertEqual(5, len(set(texts)))
        for text in texts:
            self.assertTrue(text.startswith("呜喵"))
            self.assertNotIn("！", text)  # 保持原有口吻，不堆感叹号

    def test_paid_album_is_not_reported_as_no_copyright(self):
        self.assertNotEqual(
            self.main._audio_fail_text("paid_album"),
            self.main._audio_fail_text("no_copyright"),
        )


class CardQualityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.main = plugin.Main(context=None, config={"api_url": "http://api.test", "quality": "exhigh"})

    async def asyncTearDown(self):
        await self.main.http_session.close()

    def test_shows_actual_level_format_and_bitrate(self):
        text = self.main._format_quality({"level": "exhigh", "type": "mp3", "br": 320000})
        self.assertEqual("exhigh / mp3 320k", text)

    def test_actual_level_beats_configured_quality(self):
        """配置是 exhigh，但实际拿到 standard/128k 时必须如实显示。"""
        text = self.main._format_quality({"level": "standard", "type": "mp3", "br": 128008})
        self.assertEqual("standard / mp3 128k", text)
        self.assertNotEqual("exhigh", text)

    def test_string_bitrate_is_normalized(self):
        text = self.main._format_quality({"level": "exhigh", "type": "mp3", "br": "320000"})
        self.assertEqual("exhigh / mp3 320k", text)

    def test_missing_fields_fall_back_to_config(self):
        self.assertEqual("exhigh (配置)", self.main._format_quality(None))
        self.assertEqual("exhigh (配置)", self.main._format_quality({}))


class PlaybackPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.main = plugin.Main(context=None, config={"api_url": "http://api.test", "quality": "exhigh"})

    async def asyncTearDown(self):
        await self.main.http_session.close()

    def build(self, **session_kwargs):
        session = MockSession(detail=DETAIL_PAYLOAD, **session_kwargs)
        self.main.api = plugin.NeteaseMusicAPI("http://api.test", session)
        self.main.song_cache["cache-key"] = [{"id": FREE_ID, "name": "生命線"}]
        return FakeEvent()

    async def test_trial_only_sends_text_and_no_audio(self):
        event = self.build(
            official=song_url_payload(
                url="http://cdn.test/trial45s.mp3",
                time=45035,
                free_trial={"start": 0, "end": 45},
                fee=1,
            )
        )
        status = await self.main.play_selected_song(event, "cache-key", 1)

        self.assertEqual("trial_only", status)
        self.assertEqual([], event.records())
        self.assertEqual([self.main._audio_fail_text("trial_only")], event.texts())

    async def test_full_track_keeps_normal_send_pipeline(self):
        """成功路径必须仍走 event.send(MessageChain([Record(file=...)]))。"""
        event = self.build(
            official=song_url_payload(
                url="http://cdn.test/full.mp3",
                time=FREE_DT,
                free_trial="null",
                level="exhigh",
                type="mp3",
                br=320000,
            )
        )
        status = await self.main.play_selected_song(event, "cache-key", 1)

        self.assertEqual("ok", status)
        records = event.records()
        self.assertEqual(1, len(records))
        self.assertEqual("http://cdn.test/full.mp3", records[0].file)

        card = "\n".join(event.texts())
        self.assertIn("✨ 音质：exhigh / mp3 320k", card)
        self.assertIn("⏳ 时长：", card)


if __name__ == "__main__":
    unittest.main()
