from pathlib import Path
from io import BytesIO
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from streamlit.testing.v1 import AppTest

from app import display_value, evidence_rows
from config import Settings

ROOT = Path(__file__).resolve().parents[1]


class InitialScreenTests(unittest.TestCase):
    def test_initial_screen_and_missing_upload(self):
        app = AppTest.from_file(str(ROOT / 'app.py')).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, 'DART Insight AI')
        self.assertEqual([t.label for t in app.tabs],
                         ['기업 개요', '산업 동향', '기술 & 투자', '취업 인사이트', '근거 / 원문'])
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('업로드' in i.value for i in app.info))


class UploadedScreenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'output'
        settings = patch('config.Settings.from_env', return_value=Settings())
        settings.start()
        self.addCleanup(settings.stop)
        upload = patch('streamlit.file_uploader')
        self.upload = upload.start()
        self.addCleanup(upload.stop)
        self.upload.return_value = self.make_upload('사업의 내용 연구개발 직원')
        # AppTest executes app.py in its own __main__; redirect only the output root.
        base = patch('config.BASE_DIR', Path(self.temp.name))
        base.start()
        self.addCleanup(base.stop)

    def make_upload(self, text, name='report.pdf'):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((50, 60), text, fontname='korea')
            upload = BytesIO(doc.tobytes())
        upload.name = name
        return upload

    def app(self):
        return AppTest.from_file(str(ROOT / 'app.py'), default_timeout=15).run()

    def test_uploaded_pdf_renders_five_tabs_and_separate_mock_evidence(self):
        app = self.app()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertTrue(app.success)
        self.assertEqual(len(app.tabs), 5)
        self.assertTrue(app.session_state['analysis_result']['is_mock'])
        self.assertEqual(len(list(self.output.iterdir())), 5)
        self.assertTrue(any('업로드한 PDF의 근거가 아닙니다' in w.value for w in app.warning))
        self.assertTrue(any('사업의 내용' in t.value for t in app.text))
        self.assertEqual(list(app.dataframe[0].value.columns), ['구분', 'Fact', 'Page'])

    def test_replacing_and_removing_upload_clears_previous_result(self):
        app = self.app()
        app.button[0].click().run()
        self.assertTrue(app.success)
        self.upload.return_value = self.make_upload('다른 보고서', 'new.pdf')
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.success)
        self.assertFalse(app.metric)
        app.button[0].click().run()
        self.assertTrue(app.success)
        self.upload.return_value = None
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.success)

    def test_invalid_pdf_is_friendly_and_retry_succeeds(self):
        bad = BytesIO(b'not a pdf')
        bad.name = 'bad.pdf'
        self.upload.return_value = bad
        with self.assertLogs(level='ERROR'):
            app = self.app()
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertNotIn('Traceback', app.error[0].value)
        self.upload.return_value = self.make_upload('시장 R&D')
        app.run().button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)

    def test_failed_rerun_does_not_show_previous_result(self):
        app = self.app()
        app.button[0].click().run()
        with patch('business_agent.analyze_business', side_effect=RuntimeError('private detail')), \
             self.assertLogs(level='ERROR'):
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertFalse(app.success)
        self.assertFalse(app.metric)
        self.assertNotIn('private detail', app.error[0].value)

    def test_live_mode_shows_setup_error_without_crashing(self):
        with patch('config.Settings.from_env', return_value=Settings(use_mock=False)), \
             self.assertLogs(level='ERROR'):
            app = self.app()
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertIn('USE_MOCK=true', app.error[0].value)
        self.assertFalse(app.success)

    def test_missing_numbers_and_zero_display(self):
        self.assertEqual(display_value(None), '-')
        self.assertEqual(display_value(0), '0')
        self.assertEqual(evidence_rows({'market_conditions': 'bad'}, {}), [])

    def test_studio_pdf_creation_does_not_call_agents(self):
        with patch('business_agent.analyze_business', side_effect=AssertionError('Agent must not run')), \
             patch('config.Settings.from_env', return_value=Settings(use_mock=False)):
            app = self.app()
            app.button(key='prepare_studio').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        exported = app.session_state['studio_export']
        self.assertTrue((Path(exported['directory']) / 'business_input.pdf').exists())
        self.assertTrue((Path(exported['directory']) / 'tech_input.pdf').exists())
        self.assertEqual(exported['manifest']['source_filename'], 'report.pdf')
        self.assertEqual(len(app.get('download_button')), 3)
        self.assertFalse(app.metric)

    def test_studio_result_clears_on_file_change(self):
        app = self.app()
        app.button(key='prepare_studio').click().run()
        self.assertEqual(len(app.get('download_button')), 3)
        self.upload.return_value = self.make_upload('다른 연구개발 보고서', 'new.pdf')
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.get('download_button'))

    def test_studio_no_upload_shows_guidance(self):
        self.upload.return_value = None
        app = self.app()
        app.button(key='prepare_studio').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertFalse(app.get('download_button'))
