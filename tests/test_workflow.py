import json
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

import pymupdf

from app import analyze_report
from config import Settings
from schemas import BusinessResult, TechResult, InsightResult


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.pdf = self.directory / 'report.pdf'
        with pymupdf.open() as document:
            document.new_page().insert_text((50, 60), '사업의 내용 연구개발 매출 직원', fontname='korea')
            document.save(self.pdf)
        self.out = self.directory / 'output'
        config = patch('config.Settings.from_env', return_value=Settings())
        config.start()
        self.addCleanup(config.stop)

    def test_real_pdf_to_three_jsons_and_text_files(self):
        result = analyze_report(str(self.pdf), output_dir=self.out)
        self.assertTrue(result['is_mock'])
        self.assertIn('===== PAGE 1 =====', (self.out / 'business_input.txt').read_text(encoding='utf-8'))
        for key, model in [('business', BusinessResult), ('tech', TechResult), ('insight', InsightResult)]:
            saved = json.loads((self.out / f'{key}_result.json').read_text(encoding='utf-8'))
            self.assertEqual(saved, result[key])
            model.model_validate(saved)
        self.assertEqual(len(list(self.out.iterdir())), 5)
        self.assertIn('가상', (self.out / 'business_result.json').read_text(encoding='utf-8'))

    def test_insight_gets_only_extracted_json_and_runs_after_both(self):
        order = []
        business, tech = BusinessResult().model_dump(), TechResult().model_dump()
        def b(text):
            order.append('business')
            self.assertIn('PAGE 1', text)
            return business
        def t(text):
            order.append('tech')
            return tech
        def i(actual_b, actual_t):
            order.append('insight')
            self.assertEqual(actual_b, business)
            self.assertEqual(actual_t, tech)
            return InsightResult().model_dump()
        with patch('app.analyze_business', side_effect=b), \
             patch('app.analyze_technology_and_investment', side_effect=t), \
             patch('app.generate_insight', side_effect=i):
            analyze_report(str(self.pdf), output_dir=self.out)
        self.assertCountEqual(order[:2], ['business', 'tech'])
        self.assertEqual(order[2:], ['insight'])

    def test_agent_failure_does_not_save_partial_results(self):
        with patch('app.generate_insight', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                analyze_report(str(self.pdf), output_dir=self.out)
        self.assertFalse(self.out.exists())

    def test_extracts_overlap_then_insight_merges_only_their_results(self):
        # Exercise the real preprocessor and all three wrappers; replace only transport.
        with pymupdf.open() as document:
            for text in ['매출 BUSINESS_ONLY', 'context', 'unrelated', 'unrelated',
                         'unrelated', 'context', 'R&D TECH_ONLY']:
                document.new_page().insert_text((50, 60), text, fontname='korea')
            document.save(self.pdf)
        settings = Settings(use_mock=False, business_agent_id='business-id',
                            tech_agent_id='tech-id', insight_agent_id='insight-id')
        calls = []
        # Neither Extract may finish before the other starts. Sequential code
        # breaks this rendezvous instead of passing a timing-based speed test.
        extracts_started = Barrier(2, timeout=5)

        def transport(agent_id, input_text):
            calls.append((agent_id, input_text))
            if agent_id in ('business-id', 'tech-id'):
                extracts_started.wait()
            if agent_id == 'business-id':
                return {'company_name': '연결 검증 기업'}
            if agent_id == 'tech-id':
                return {'technology_keywords': ['검증 기술'], 'employee_count': 17}
            if agent_id == 'insight-id':
                payload = json.loads(input_text)
                self.assertEqual(set(payload), {'business', 'technology_and_investment'})
                self.assertEqual(payload['business'], BusinessResult(
                    company_name='연결 검증 기업').model_dump())
                self.assertEqual(payload['technology_and_investment'], TechResult(
                    technology_keywords=['검증 기술'], employee_count=17).model_dump())
                return {'summary': '두 Extract 결과 전달 확인'}
            self.fail(f'Unexpected agent ID: {agent_id}')

        with patch('config.Settings.from_env', return_value=settings), \
             patch('business_agent.run_agent', side_effect=transport), \
             patch('tech_agent.run_agent', side_effect=transport), \
             patch('agent_client.run_agent', side_effect=transport):
            result = analyze_report(str(self.pdf), output_dir=self.out)

        self.assertCountEqual([item[0] for item in calls[:2]], ['business-id', 'tech-id'])
        self.assertEqual(calls[2][0], 'insight-id')
        inputs = dict(calls)
        self.assertIn('BUSINESS_ONLY', inputs['business-id'])
        self.assertNotIn('TECH_ONLY', inputs['business-id'])
        self.assertIn('TECH_ONLY', inputs['tech-id'])
        self.assertNotIn('BUSINESS_ONLY', inputs['tech-id'])
        self.assertNotIn('PAGE ', calls[2][1])
        self.assertFalse(result['is_mock'])
        saved = json.loads((self.out / 'insight_result.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['summary'], '두 Extract 결과 전달 확인')

    def test_either_extract_failure_preserves_last_success_and_skips_insight(self):
        analyze_report(str(self.pdf), output_dir=self.out)
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        settings = Settings(use_mock=False, business_agent_id='business-id',
                            tech_agent_id='tech-id', insight_agent_id='insight-id')
        for failing_id in ('business-id', 'tech-id'):
            with self.subTest(failing_id=failing_id):
                extracts_started = Barrier(2, timeout=5)
                calls = []

                def transport(agent_id, input_text):
                    calls.append(agent_id)
                    if agent_id in ('business-id', 'tech-id'):
                        extracts_started.wait()
                    if agent_id == failing_id:
                        raise RuntimeError('extract failure')
                    return {}

                with patch('config.Settings.from_env', return_value=settings), \
                     patch('business_agent.run_agent', side_effect=transport), \
                     patch('tech_agent.run_agent', side_effect=transport), \
                     patch('agent_client.run_agent', side_effect=transport):
                    with self.assertRaisesRegex(RuntimeError, 'extract failure'):
                        analyze_report(str(self.pdf), output_dir=self.out)
                self.assertCountEqual(calls, ['business-id', 'tech-id'])
                self.assertEqual({p.name: p.read_bytes() for p in self.out.iterdir()}, before)

    def test_save_error_is_reported(self):
        self.out.write_text('file blocking directory')
        with self.assertRaises(OSError):
            analyze_report(str(self.pdf), output_dir=self.out)

    def test_mid_save_failure_restores_previous_success(self):
        analyze_report(str(self.pdf), output_dir=self.out)
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        updated = BusinessResult(company_name='changed').model_dump()
        original_replace = Path.replace
        count = 0
        def fail_third(source, destination):
            nonlocal count
            count += 1
            if count == 3:
                raise PermissionError('locked result')
            return original_replace(source, destination)
        with patch('app.analyze_business', return_value=updated), \
             patch.object(Path, 'replace', fail_third):
            with self.assertRaises(PermissionError):
                analyze_report(str(self.pdf), output_dir=self.out)
        after = {p.name: p.read_bytes() for p in self.out.iterdir()}
        self.assertEqual(before, after)

    def test_mid_save_failure_on_first_run_leaves_no_partial_files(self):
        original_replace = Path.replace
        count = 0
        def fail_third(source, destination):
            nonlocal count
            count += 1
            if count == 3:
                raise PermissionError('locked result')
            return original_replace(source, destination)
        with patch.object(Path, 'replace', fail_third):
            with self.assertRaises(PermissionError):
                analyze_report(str(self.pdf), output_dir=self.out)
        self.assertEqual(list(self.out.iterdir()), [])
