"""PR1-1 回归：会员曲试听片段 / 残片绝不能被当成整首返回。"""

import unittest

from _support import LOG, MockSession, load_plugin, song_url_payload

plugin = load_plugin()

MEMBER_ID = 1869929814
MEMBER_DT = 255582  # 4:15，会员曲
FREE_ID = 450048197
FREE_DT = 1083141
TOLERANCE = max(2000, MEMBER_DT * 0.02)  # 5111.64ms


class AudioResultTests(unittest.IsolatedAsyncioTestCase):
    def api(self, **kwargs):
        session = MockSession(**kwargs)
        return plugin.NeteaseMusicAPI("http://api.test", session), session

    async def test_vip_trial_is_never_returned_as_ok(self):
        """官方只回 45s 试听时不得返回 ok，且 url 必须为 None。"""
        api, _ = self.api(
            official=song_url_payload(
                url="http://cdn.test/trial45s.mp3",
                time=45035,
                free_trial={"start": 0, "end": 45},
                fee=1,
            )
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("trial_only", result.status)
        self.assertIsNone(result.url)

    async def test_trial_length_drift_30s_also_blocked(self):
        """试听长度会漂移（45s/30s），同样不得返回。"""
        api, _ = self.api(
            official=song_url_payload(
                url="http://cdn.test/trial30s.mp3",
                time=30040,
                free_trial={"start": 0, "end": 30},
                fee=1,
            )
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertNotEqual("ok", result.status)
        self.assertIsNone(result.url)

    async def test_free_trial_string_null_is_full_track(self):
        """freeTrialInfo 是字符串 "null" 时视为整首（该服务端的实际返回形态）。"""
        api, _ = self.api(
            official=song_url_payload(
                url="http://cdn.test/full.mp3", time=FREE_DT, free_trial="null"
            )
        )
        result = await api.get_audio_url(FREE_ID, "exhigh", "", FREE_DT)
        self.assertEqual("ok", result.status)
        self.assertEqual("http://cdn.test/full.mp3", result.url)

    async def test_empty_free_trial_object_is_full_track(self):
        """freeTrialInfo 是空对象 {} 时必须视为整首，不能判成试听。"""
        api, _ = self.api(
            official=song_url_payload(
                url="http://cdn.test/full.mp3", time=FREE_DT, free_trial={}
            )
        )
        result = await api.get_audio_url(FREE_ID, "exhigh", "", FREE_DT)
        self.assertEqual("ok", result.status)
        self.assertEqual("http://cdn.test/full.mp3", result.url)

    async def test_empty_free_trial_list_is_full_track(self):
        """freeTrialInfo 是空数组 [] 同理。"""
        api, _ = self.api(
            official=song_url_payload(
                url="http://cdn.test/full.mp3", time=FREE_DT, free_trial=[]
            )
        )
        result = await api.get_audio_url(FREE_ID, "exhigh", "", FREE_DT)
        self.assertEqual("ok", result.status)
        self.assertIsNotNone(result.url)

    async def test_string_time_field_is_normalized(self):
        """time 是字符串（"255582"）时不能 TypeError。"""
        api, _ = self.api(
            official=song_url_payload(
                url="http://cdn.test/full.mp3", time=str(MEMBER_DT), free_trial=None
            )
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("ok", result.status)
        self.assertEqual("http://cdn.test/full.mp3", result.url)

    async def test_missing_free_trial_but_short_time_is_rejected(self):
        """freeTrialInfo 为 None 但 time 远小于 dt：残片同样不得返回。"""
        api, _ = self.api(
            official=song_url_payload(url="http://cdn.test/clip.mp3", time=30040)
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertNotEqual("ok", result.status)
        self.assertIsNone(result.url)

    async def test_time_inside_tolerance_is_accepted(self):
        """time 与 dt 相差在 max(2s, 2%) 容差内，不应误杀。"""
        api, _ = self.api(
            official=song_url_payload(url="http://cdn.test/near.mp3", time=MEMBER_DT - 3000)
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("ok", result.status)
        self.assertEqual("http://cdn.test/near.mp3", result.url)

    async def test_time_outside_tolerance_is_rejected(self):
        """刚好越过容差边界就要判残片。"""
        just_outside = int(MEMBER_DT - TOLERANCE) - 1
        api, _ = self.api(
            official=song_url_payload(url="http://cdn.test/short.mp3", time=just_outside)
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("trial_only", result.status)
        self.assertIsNone(result.url)

    async def test_unknown_duration_skips_time_check(self):
        """调用方没传 dt 时不按 time 判残片，试听仍由 freeTrialInfo 拦住。"""
        api, _ = self.api(
            official=song_url_payload(
                url="http://cdn.test/trial.mp3", time=30040, free_trial={"start": 0, "end": 30}
            )
        )
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", 0)
        self.assertEqual("trial_only", result.status)
        self.assertIsNone(result.url)

    async def test_paid_album_status(self):
        """fee=4 是付费数字专辑，单独归类，不并入"没版权"。"""
        api, _ = self.api(official=song_url_payload(url=None, fee=4))
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("paid_album", result.status)
        self.assertIsNone(result.url)

    async def test_no_copyright_status(self):
        """code=404 才是无版权/无资源。"""
        api, _ = self.api(official=song_url_payload(url=None, code=404, fee=0))
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("no_copyright", result.status)
        self.assertIsNone(result.url)

    async def test_unavailable_status(self):
        """接口能正常响应、但所有档位都没有可播地址 -> unavailable。"""
        api, _ = self.api(official=song_url_payload(url=None, code=200, fee=0))
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("unavailable", result.status)
        self.assertIsNone(result.url)

    async def test_upstream_error_when_all_requests_fail(self):
        """全部请求异常 -> upstream_error，而不是静默返回 None。"""
        api, _ = self.api(official=RuntimeError("connection refused"))
        result = await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        self.assertEqual("upstream_error", result.status)
        self.assertIsNone(result.url)

    async def test_error_log_does_not_leak_cookie(self):
        """异常字符串里带 cookie 时，日志不能把 cookie 写出去。"""
        LOG.records.clear()
        api, _ = self.api(official=RuntimeError(
            "502 Server Error: http://api.test/song/url/v1?id=1&level=exhigh&cookie=MUSIC_U=SECRET"
        ))
        await api.get_audio_url(MEMBER_ID, "exhigh", "MUSIC_U=SECRET", MEMBER_DT)
        joined = "\n".join(text for _, text in LOG.records)
        self.assertNotIn("SECRET", joined)
        self.assertIn("RuntimeError", joined)

    async def test_cookie_is_forwarded_to_every_request(self):
        """cookie 是已合入的特性，回归它不因本次改动丢失。"""
        api, session = self.api(official=song_url_payload(url=None, code=200, fee=0))
        await api.get_audio_url(MEMBER_ID, "exhigh", "MUSIC_U=abc123", MEMBER_DT)
        self.assertTrue(session.calls)
        for url, _ in session.calls:
            self.assertIn("cookie=MUSIC_U=abc123", url)

    async def test_quality_fallback_order_preserved(self):
        """仍按 quality -> exhigh -> higher -> standard 顺序探测（去重后 3 档）。"""
        api, session = self.api(official=song_url_payload(url=None, code=200, fee=0))
        await api.get_audio_url(MEMBER_ID, "exhigh", "", MEMBER_DT)
        levels = [url.split("level=")[1].split("&")[0] for url, _ in session.calls]
        self.assertEqual(["exhigh", "higher", "standard"], levels)


if __name__ == "__main__":
    unittest.main()
