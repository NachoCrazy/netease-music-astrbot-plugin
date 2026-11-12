"""AstrBot renders description as the title and hint as its help text."""
import json
from pathlib import Path
import unittest

SCHEMA = Path(__file__).resolve().parents[1] / '_conf_schema.json'


class ConfigMetadataTests(unittest.TestCase):
    def test_titles_and_help_are_separate(self):
        schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
        titles = {
            'api_url': '网易云 API 地址',
            'quality': '优先音质',
            'search_limit': '搜索结果数量',
            'send_cover': '发送封面图',
            'send_song_info': '发送歌曲信息',
            'cookie': '网易云 Cookie',
        }
        self.assertEqual(set(schema), set(titles))
        for key, title in titles.items():
            with self.subTest(key=key):
                self.assertEqual(schema[key]['description'], title)
                self.assertTrue(schema[key].get('hint', '').strip(), 'Keep usage instructions below the title')

    def test_types_and_defaults_remain_compatible(self):
        schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
        expected = {
            'api_url': ('string', 'http://127.0.0.1:3000'),
            'quality': ('string', 'exhigh'),
            'search_limit': ('int', 5),
            'send_cover': ('bool', True),
            'send_song_info': ('bool', True),
            'cookie': ('text', ''),
        }
        for key, (field_type, default) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(schema[key]['type'], field_type)
                self.assertEqual(schema[key]['default'], default)


if __name__ == '__main__':
    unittest.main()
