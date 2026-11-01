"""解灰(unblock)补全整首的回归用例：可选能力，失败时必须回落到明确状态。"""

import asyncio
import time
import unittest

from _support import MockSession, load_plugin, song_url_payload

plugin = load_plugin()

MEMBER_ID = 1869929814
MEMBER_DT = 255582
FREE_ID = 450048197
FREE_DT = 1083141


class _HangingResponse:
    async def __aenter__(self):
        await asyncio.sleep(5)
        raise AssertionError("总闸没生效：请求没有被取消")

    async def __aexit__(self, *exc_info):
        return False


class HangingSession:
    """所有请求都挂住的会话替身，用来触发整段取流的总预算。"""

    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs.get("timeout")))
        return _HangingResponse()


class UnblockTests(unittest.IsolatedAsyncioTestCase):
    def api(self, **kwargs):
        session = MockSession(**kwargs)
        return plugin.NeteaseMusicAPI("http://api.test", session), session

    async def test_trial_song_is_completed_by_unblock(self):
        """官方只给试听时，解灰补全整首 -> ok，且标注来源为"解灰"。"""
        api, session = self.api(
            official=song_url_payload(
                url="http://cdn.test/trial45s.mp3", time=45035,
                free_trial={"start": 0, "end": 45}, fee=1,
            ),
            unblock={"data": [{"url": "http://cdn.test/unblock.flac", "freeTrialInfo": "null",
                               "level": "exhigh", "type": "flac"}]},
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("ok", result.status)
        self.assertEqual("http://cdn.test/unblock.flac", result.url)
        self.assertEqual("解灰", result.info.get("_card_level"))
        self.assertTrue(any("unblock=true" in url for url, _ in session.calls))

    async def test_unblock_success_without_time_field(self):
        """解灰成功响应通常不含 time，此时以 freeTrialInfo 为准判成功。"""
        api, _ = self.api(
            official=song_url_payload(url=None, code=200, fee=1),
            unblock={"data": [{"url": "http://cdn.test/unblock.mp3", "freeTrialInfo": "null"}]},
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("ok", result.status)
        self.assertEqual("http://cdn.test/unblock.mp3", result.url)

    async def test_unblock_truncated_track_is_rejected(self):
        """解灰拿回来仍是残片（time 远小于 dt）时不得判成功。"""
        api, _ = self.api(
            official=song_url_payload(url=None),
            unblock={"data": [{"url": "http://cdn.test/short.flac", "time": 60000,
                               "freeTrialInfo": None, "level": "exhigh"}]},
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertNotEqual("ok", result.status)
        self.assertIsNone(result.url)

    async def test_unblock_timeout_falls_back_to_trial_only(self):
        """解灰超时时：有试听记录 -> trial_only，绝不能把试听地址返回。"""
        api, _ = self.api(
            official=song_url_payload(
                url="http://cdn.test/trial45s.mp3", time=45035,
                free_trial={"start": 0, "end": 45}, fee=1,
            ),
            unblock=asyncio.TimeoutError("unblock budget exceeded"),
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("trial_only", result.status)
        self.assertIsNone(result.url)

    async def test_unblock_failed_status_without_trial(self):
        """官方无可播地址、解灰又失败 -> unblock_failed。"""
        api, _ = self.api(
            official=song_url_payload(url=None, code=200, fee=0),
            unblock=asyncio.TimeoutError("unblock budget exceeded"),
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("unblock_failed", result.status)
        self.assertIsNone(result.url)

    async def test_all_official_failures_skip_unblock(self):
        """官方三档全挂时短路，不得再发解灰请求（否则要静默几十秒）。"""
        api, session = self.api(
            official=RuntimeError("connection refused"),
            unblock=RuntimeError("connection refused"),
        )
        started = time.monotonic()
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        elapsed = time.monotonic() - started
        self.assertEqual("upstream_error", result.status)
        self.assertIsNone(result.url)
        self.assertFalse([u for u, _ in session.calls if "unblock=true" in u],
                         f"不应发起解灰请求: {session.calls}")
        self.assertLess(elapsed, 1.0)

    async def test_proxy_url_is_used_when_url_missing(self):
        """ENABLE_PROXY：官方响应 url 为空、真实地址在 proxyUrl。"""
        api, _ = self.api(
            official=song_url_payload(url=None, time=FREE_DT, free_trial=None,
                                      proxyUrl="http://cdn.test/proxy.mp3")
        )
        result = await api.get_audio_url(FREE_ID, "exhigh", "", FREE_DT)
        self.assertEqual("ok", result.status)
        self.assertEqual("http://cdn.test/proxy.mp3", result.url)

    async def test_proxy_url_used_for_unblock_response(self):
        """解灰响应同样支持 proxyUrl。"""
        api, _ = self.api(
            official=song_url_payload(url=None, code=200, fee=1),
            unblock={"data": [{"url": None, "freeTrialInfo": "null",
                               "proxyUrl": "http://cdn.test/unblock_proxy.mp3"}]},
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("ok", result.status)
        self.assertEqual("http://cdn.test/unblock_proxy.mp3", result.url)

    async def test_cookie_is_forwarded_to_unblock_request(self):
        """cookie 必须也带到解灰请求上（否则 VIP 解灰可能失效）。"""
        api, session = self.api(
            official=song_url_payload(url=None, code=200, fee=1),
            unblock={"data": [{"url": "http://cdn.test/u.mp3", "freeTrialInfo": "null"}]},
        )
        await api.get_audio_url(MEMBER_ID, "exhigh", "MUSIC_U=abc123", MEMBER_DT)
        unblock_urls = [u for u, _ in session.calls if "unblock=true" in u]
        self.assertTrue(unblock_urls)
        for url in unblock_urls:
            self.assertIn("cookie=MUSIC_U=abc123", url)

    async def test_unblock_request_has_its_own_budget(self):
        """解灰请求带独立 timeout（30s），不继承普通请求预算。"""
        api, session = self.api(
            official=song_url_payload(url=None, code=200, fee=1),
            unblock={"data": [{"url": "http://cdn.test/u.mp3", "freeTrialInfo": "null"}]},
        )
        await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        budgets = [t for u, t in session.calls if "unblock=true" in u]
        self.assertEqual(1, len(budgets))
        self.assertIs(plugin.UNBLOCK_TIMEOUT, budgets[0])
        self.assertEqual(30, plugin.UNBLOCK_TIMEOUT.total)

    async def test_whole_probe_has_total_budget(self):
        """上游一直挂住时，整段取流会被总闸取消并按 upstream_error 返回。"""
        original = plugin.AUDIO_TOTAL_BUDGET
        plugin.AUDIO_TOTAL_BUDGET = 0.05  # 测试里把 40s 压成 50ms
        try:
            api = plugin.NeteaseMusicAPI("http://api.test", HangingSession())
            started = time.monotonic()
            result = await api.get_audio_url(1, "exhigh", "", 1000)
            elapsed = time.monotonic() - started
        finally:
            plugin.AUDIO_TOTAL_BUDGET = original

        self.assertEqual("upstream_error", result.status)
        self.assertIsNone(result.url)
        self.assertLess(elapsed, 1.0)


class FailTextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.main = plugin.Main(context=None, config={"api_url": "http://api.test"})

    async def asyncTearDown(self):
        await self.main.http_session.close()

    def test_unblock_failed_text_differs_from_trial_text(self):
        self.assertNotEqual(
            self.main._audio_fail_text("trial_only"),
            self.main._audio_fail_text("unblock_failed"),
        )

    def test_unblock_failed_does_not_mention_trial(self):
        """解灰失败时往往连试听都拿不到，不能说"只能听试听"。"""
        self.assertNotIn("试听", self.main._audio_fail_text("unblock_failed"))

    def test_unblock_quality_label(self):
        """解灰来源标"解灰"，不冒充 exhigh。"""
        text = self.main._format_quality({"_card_level": "解灰", "level": "exhigh", "type": "flac"})
        self.assertEqual("解灰 / flac", text)


if __name__ == "__main__":
    unittest.main()
