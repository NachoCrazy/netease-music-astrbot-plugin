"""Offline tests of the real API wrapper and send method; no AstrBot dependency."""
import ast
import base64
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
api_node = next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='NeteaseMusicAPI')
future = ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
namespace = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=[future,api_node],type_ignores=[])),'<real-api-wrapper>','exec'),namespace)
API = namespace['NeteaseMusicAPI']

class Session:
    def __init__(self, available=None, statuses=None, payload=None):
        self.available, self.statuses, self.payload = available, statuses or {}, payload
        self.queries = []

    def get(self, url):
        query = parse_qs(urlparse(url).query)
        self.queries.append(query)
        level = query['level'][0]
        owner = self
        class Response:
            status = owner.statuses.get(level,200)
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            def raise_for_status(self):
                if self.status >= 400: raise RuntimeError('HTTP error')
            async def json(self):
                if owner.payload is not None: return owner.payload
                return {'data':[{'url':'https://example.invalid/audio' if level==owner.available else None}]}
        return Response()

class QualityTests(unittest.IsolatedAsyncioTestCase):
    def test_chinese_codes_and_client_aliases(self):
        aliases = ['Standard','Higher','HQ','SQ','Hi-Res','Spatial Audio','Dolby Atmos','Audio Vivid','Master','Surround Audio']
        self.assertEqual(len(API.QUALITY_LABELS),10)
        for (code,chinese),alias in zip(API.QUALITY_LABELS.items(),aliases):
            with self.subTest(code=code):
                for value in (code.upper(),chinese,alias,alias.lower()):
                    self.assertEqual(API.normalize_quality(value),code)
                self.assertEqual(API.quality_label(code),chinese)
        self.assertEqual(API.normalize_quality(' Hi-Res '),'hires')
        with self.assertRaises(ValueError): API.normalize_quality('not-a-quality')

    async def test_chinese_requests_use_api_codes(self):
        for code,label in API.QUALITY_LABELS.items():
            with self.subTest(code=code):
                session = Session(available=code)
                self.assertTrue(await API('http://localhost',session).get_audio_url(1,label))
                self.assertEqual([q['level'][0] for q in session.queries],[code])

    async def test_ordinary_levels_never_upgrade(self):
        session = Session(available='standard')
        self.assertTrue(await API('http://localhost',session).get_audio_url(1,'无损'))
        self.assertEqual([q['level'][0] for q in session.queries],['lossless','exhigh','higher','standard'])
        self.assertEqual(API.quality_candidates('标准'),['standard'])
        self.assertEqual(API.quality_candidates('higher'),['higher','standard'])

    async def test_effect_formats_fall_back_to_ordinary_levels(self):
        session = Session(available='lossless',statuses={'sky':403,'hires':404})
        self.assertTrue(await API('http://localhost',session).get_audio_url(1,'Surround Audio'))
        self.assertEqual([q['level'][0] for q in session.queries],['sky','hires','lossless'])

    async def test_unsupported_level_response_can_downgrade(self):
        session = Session(available='exhigh',statuses={'hires':400,'lossless':403})
        self.assertTrue(await API('http://localhost',session).get_audio_url(1,'Hi-Res'))

    async def test_empty_missing_and_null_data(self):
        for payload in ({'data':[]},{'data':None},{'code':200}):
            with self.subTest(payload=payload):
                session = Session(payload=payload)
                self.assertIsNone(await API('http://localhost',session).get_audio_url(1,'Master'))
                levels = [q['level'][0] for q in session.queries]
                self.assertEqual(len(levels),len(set(levels)))

    async def test_server_errors_are_not_swallowed(self):
        session = Session(statuses={'hires':500})
        with self.assertRaises(RuntimeError):
            await API('http://localhost',session).get_audio_url(1,'hires')

    async def test_cookie_parameter_is_preserved(self):
        session = Session(available='exhigh')
        await API('http://localhost',session).get_audio_url(1,'HQ',cookie='test-cookie')
        self.assertEqual(session.queries[0]['cookie'],['test-cookie'])

    def test_dropdown_labels_defaults_and_no_manual_override(self):
        schema = json.loads((ROOT/'_conf_schema.json').read_text(encoding='utf-8'))
        quality = schema['quality']
        self.assertEqual(quality['options'],list(API.QUALITY_LABELS))
        self.assertEqual(quality['default'],'exhigh')
        self.assertEqual(len(quality['labels']),10)
        self.assertNotIn('quality_custom',schema)
        for label in quality['labels']:
            self.assertIn('（',label)
            self.assertTrue(any(unit in label for unit in ('kbps','kHz','声道')))
        self.assertIn('44.1–48kHz / 16bit',quality['labels'][3])
        self.assertIn('48–192kHz / 24bit',quality['labels'][4])
        self.assertIn('最高7.1.4声道',quality['labels'][6])

    async def test_playback_text_marks_preference_and_sends_voice(self):
        cls = next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='Main')
        method = next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_send_song_messages')
        messages = []
        async def send(message): messages.append(message)
        async def download(url): return None
        api = SimpleNamespace(download_image=download,quality_label=API.quality_label)
        owner = SimpleNamespace(config={'quality':'Master'},api=api)
        ns = {'base64':base64,'Plain':lambda text:('plain',text),'Record':lambda **kwargs:('record',kwargs),'MessageChain':list}
        code = ast.Module(body=[future,method],type_ignores=[])
        exec(compile(ast.fix_missing_locations(code),'<real-send-method>','exec'),ns)
        await ns['_send_song_messages'](owner,SimpleNamespace(send=send),1,'song','artist','album','1:00','','https://example.invalid/audio')
        self.assertIn('优先音质：超清母带',messages[0][0][1])
        self.assertEqual(messages[-1][0][0],'record')

if __name__=='__main__': unittest.main()
