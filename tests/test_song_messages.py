"""Test the real send method without an AstrBot runtime or network access.

Only external message types and the event transport are stubbed. Extracting the
method avoids importing AstrBot or creating an aiohttp session in these tests.
Run: python -m unittest discover -s tests -v
"""
import ast
import base64
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_send_method():
    source = (ROOT / 'main.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Main')
    method = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == '_send_song_messages')
    for arg in method.args.args:
        arg.annotation = None
    method.returns = None
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = {
        'base64': base64,
        'Plain': lambda text: ('plain', text),
        'Image': SimpleNamespace(fromBase64=lambda data: ('image', data)),
        'Record': lambda **kwargs: ('record', kwargs),
        'MessageChain': list,
        'logger': SimpleNamespace(warning=lambda message: None),
    }
    exec(compile(module, str(ROOT / 'main.py'), 'exec'), namespace)
    return namespace['_send_song_messages']


class SongMessageTests(unittest.IsolatedAsyncioTestCase):
    async def send_song(self, config, image_data=b'cover', voice_error=None):
        messages, downloads = [], []

        async def download_image(url):
            downloads.append(url)
            return image_data

        async def send(message):
            if any(component[0] == 'record' for component in message) and voice_error:
                raise voice_error
            messages.append(message)

        owner = SimpleNamespace(
            config={'quality': 'higher', **config},
            api=SimpleNamespace(download_image=download_image),
        )
        event = SimpleNamespace(send=send)
        await load_send_method()(owner, event, 1, 'song', 'artist', 'album', '1:00',
                                 'https://example.invalid/cover', 'https://example.invalid/audio')
        return messages, downloads

    async def test_independent_toggles(self):
        for cover in (False, True):
            for info in (False, True):
                with self.subTest(cover=cover, info=info):
                    messages, downloads = await self.send_song({'send_cover': cover, 'send_song_info': info})
                    components = [component for message in messages for component in message]
                    self.assertEqual(sum(c[0] == 'image' for c in components), int(cover))
                    self.assertEqual(sum(c[0] == 'plain' for c in components), int(info))
                    self.assertEqual(sum(c[0] == 'record' for c in components), 1)
                    self.assertEqual(len(downloads), int(cover))
                    self.assertTrue(all(messages), 'Do not send empty message chains')
                    self.assertEqual(len(messages), 2 if cover or info else 1)

    async def test_missing_options_preserve_existing_behavior(self):
        messages, downloads = await self.send_song({})
        self.assertEqual([c[0] for c in messages[0]], ['plain', 'image'])
        self.assertEqual(messages[1][0][0], 'record')
        self.assertEqual(len(downloads), 1)

    async def test_missing_cover_does_not_send_empty_message(self):
        messages, _ = await self.send_song({'send_cover': True, 'send_song_info': False}, image_data=None)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][0][0], 'record')

    async def test_voice_fallback_remains_available(self):
        messages, downloads = await self.send_song(
            {'send_cover': False, 'send_song_info': False}, voice_error=RuntimeError('ffmpeg not found'))
        self.assertEqual(downloads, [])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][0][0], 'plain')
        self.assertIn('https://example.invalid/audio', messages[0][0][1])

    async def test_unrelated_voice_error_is_not_swallowed(self):
        with self.assertRaisesRegex(RuntimeError, 'transport failed'):
            await self.send_song({'send_cover': False, 'send_song_info': False},
                                 voice_error=RuntimeError('transport failed'))

    def test_schema_defaults_preserve_existing_behavior(self):
        schema = json.loads((ROOT / '_conf_schema.json').read_text(encoding='utf-8'))
        for key in ('send_cover', 'send_song_info'):
            with self.subTest(key=key):
                self.assertEqual(schema[key]['type'], 'bool')
                self.assertIs(schema[key]['default'], True)


if __name__ == '__main__':
    unittest.main()
