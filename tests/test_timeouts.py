"""PR1-3 回归：请求超时拆分（不再共用一个 total=20 的总预算）。"""

import unittest

from _support import MockSession, load_plugin, song_url_payload

plugin = load_plugin()


class TimeoutBudgetTests(unittest.IsolatedAsyncioTestCase):
    def test_module_level_budgets(self):
        self.assertEqual(20, plugin.SEARCH_TIMEOUT.total)
        self.assertEqual(15, plugin.REQUEST_TIMEOUT.total)

    def test_search_keeps_original_20s(self):
        """搜索保留原有 20s，不跟着普通请求一起收紧到 15s。"""
        self.assertEqual(20, plugin.SEARCH_TIMEOUT.total)
        self.assertGreater(plugin.SEARCH_TIMEOUT.total, plugin.REQUEST_TIMEOUT.total)

    async def test_session_has_no_total_cap(self):
        """会话不再设 total，否则一次慢请求会把后续请求一起拖垮。"""
        main = plugin.Main(context=None, config={"api_url": "http://api.test"})
        try:
            timeout = main.http_session.timeout
            self.assertIsNone(timeout.total)
            self.assertEqual(10, timeout.connect)
            self.assertEqual(10, timeout.sock_connect)
            self.assertEqual(45, timeout.sock_read)
        finally:
            await main.http_session.close()

    async def test_each_request_carries_its_own_budget(self):
        session = MockSession(
            search={"result": {"songs": []}},
            detail={"songs": [{"id": 1, "name": "x", "ar": [], "al": {"name": "y"}, "dt": 1000}]},
            image={},
            official=song_url_payload(url="http://cdn.test/full.mp3", time=1000),
        )
        api = plugin.NeteaseMusicAPI("http://api.test", session)

        await api.search_songs("keyword", 5)
        await api.get_song_details(1)
        await api.download_image("http://img.test/cover.jpg")
        await api.get_audio_url(1, "exhigh", "")

        search = [budget for url, budget in session.calls if "/search" in url]
        others = [budget for url, budget in session.calls if "/search" not in url]

        self.assertTrue(search)
        self.assertTrue(all(budget is plugin.SEARCH_TIMEOUT for budget in search))
        self.assertGreaterEqual(len(others), 3)  # 详情 + 封面 + 官方音源
        self.assertTrue(all(budget is plugin.REQUEST_TIMEOUT for budget in others))


if __name__ == "__main__":
    unittest.main()
