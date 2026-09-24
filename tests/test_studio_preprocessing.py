import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from preprocessor import preprocess_report, export_report_for_studio


class StudioPreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / 'report.pdf'

    def write_report(self, with_bookmarks=True):
        texts = [
            '반 기 보 고 서\n교육용 기업 / 2026 반기',
            'I. 회사의 개요\n1. 회사의 개요\n기업 소개',
            'II. 사업의 내용\n1. 사업의 개요\n시장 매출 100',
            '2. 원재료 및 생산설비\n설비투자 20',
            '3. 주요계약 및 연구개발활동\n연구개발 과제 A',
            '과제 A 후속 표\n끝까지 보존되는 내용',
            'III. 재무에 관한 사항\n1. 요약재무정보\n매출 100 영업이익 10',
            '2. 재무제표 주석\n시장 매출 임직원 주식보상',
            '주석만 계속\n시장 매출 임직원 주식보상',
            'VIII. 임원 및 직원 등에 관한 사항\n1. 임원 및 직원 등의 현황\n임원 명단',
            '(3) 직원 현황\n직원 50명',
            '직원 현황표 계속\n직원 관련 후속 설명',
            '2. 임원의 보수 등\n임원 보수 100',
        ]
        with pymupdf.open() as doc:
            for i, text in enumerate(texts):
                page = doc.new_page()
                page.insert_text((40, 50), text, fontname='korea')
                page.draw_rect(pymupdf.Rect(40, 140, 300, 180), color=(0, 0, 0))
                page.insert_text((45, 160), f'table-{i+1}')
            if with_bookmarks:
                doc.set_toc([
                    [1, '반 기 보 고 서', 1], [1, 'I. 회사의 개요', 2],
                    [2, '1. 회사의 개요', 2], [1, 'II. 사업의 내용', 3],
                    [2, '1. 사업의 개요', 3], [2, '2. 원재료 및 생산설비', 4],
                    [2, '3. 주요계약 및 연구개발활동', 5],
                    [1, 'III. 재무에 관한 사항', 7], [2, '1. 요약재무정보', 7],
                    [2, '2. 재무제표 주석', 8],
                    [1, 'VIII. 임원 및 직원 등에 관한 사항', 10],
                    [2, '1. 임원 및 직원 등의 현황', 10], [2, '2. 임원의 보수 등', 13],
                ])
            doc.save(self.pdf)

    def test_sections_exclude_financial_notes_and_keep_late_employees(self):
        self.write_report()
        result = preprocess_report(str(self.pdf))
        self.assertEqual(result['selection_method'], 'pdf_bookmarks')
        self.assertEqual(result['business_pages'], [1, 2, 3, 4, 5, 6])
        for number in [5, 6, 7, 11, 12]:
            self.assertIn(number, result['tech_pages'])
        for number in [8, 9, 13]:
            self.assertNotIn(number, result['tech_pages'])
        self.assertIn('직원 50명', result['tech_text'])
        self.assertIn('끝까지 보존되는 내용', result['tech_text'])

    def test_heading_fallback_without_bookmarks(self):
        self.write_report(with_bookmarks=False)
        result = preprocess_report(str(self.pdf))
        self.assertEqual(result['selection_method'], 'text_headings')
        self.assertIn(12, result['tech_pages'])
        self.assertNotIn(9, result['business_pages'])

    def test_company_overview_in_financial_notes_is_not_shared(self):
        for with_bookmarks in (True, False):
            with self.subTest(with_bookmarks=with_bookmarks):
                self.write_report(with_bookmarks=with_bookmarks)
                with pymupdf.open(self.pdf) as doc:
                    doc[8].insert_text((40, 30), '1. 회사의 개요', fontname='korea')
                    if with_bookmarks:
                        toc = doc.get_toc()
                        index = next(i for i, row in enumerate(toc) if row[2] == 10)
                        toc.insert(index, [3, '1. 회사의 개요', 9])
                        doc.set_toc(toc)
                    doc.saveIncr()
                result = preprocess_report(str(self.pdf))
                for key in ('business_pages', 'tech_pages'):
                    self.assertIn(2, result[key])
                    self.assertNotIn(9, result[key])

    def test_export_preserves_tables_source_pages_and_all_selected_text(self):
        self.write_report()
        original = self.pdf.read_bytes()
        exported = export_report_for_studio(str(self.pdf), output_dir=self.root / 'out')
        manifest = json.loads((Path(exported['directory']) / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.pdf.read_bytes(), original)
        with pymupdf.open(self.pdf) as source:
            for key in ('business', 'tech'):
                info = manifest['files'][key]
                with pymupdf.open(Path(exported['directory']) / info['filename']) as target:
                    self.assertEqual(target.page_count, len(info['source_pages']))
                    for index, number in enumerate(info['source_pages']):
                        text = target[index].get_text()
                        self.assertIn(f'SOURCE PDF PAGE {number}', text)
                        self.assertIn(f'table-{number}', text)
                        self.assertTrue(target[index].get_drawings())
                        for line in source[number - 1].get_text().splitlines():
                            self.assertIn(line, text)

    def test_pdf_export_is_not_subject_to_text_limit(self):
        self.write_report()
        with patch('preprocessor.MAX_INPUT_CHARS', 64):
            exported = export_report_for_studio(str(self.pdf), output_dir=self.root / 'out')
        manifest = exported['manifest']
        self.assertIn(12, manifest['files']['tech']['source_pages'])
        with pymupdf.open(Path(exported['directory']) / 'tech_input.pdf') as doc:
            self.assertIn('직원 관련 후속 설명', ''.join(p.get_text() for p in doc))

    def test_missing_matches_does_not_create_empty_or_whole_document_pdf(self):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((40, 50), 'Unrelated document')
            doc.save(self.pdf)
        with self.assertRaisesRegex(ValueError, '선별'):
            export_report_for_studio(str(self.pdf), output_dir=self.root / 'out')

    def test_each_export_has_its_own_output_directory(self):
        self.write_report()
        first = export_report_for_studio(str(self.pdf), output_dir=self.root / 'out')
        second = export_report_for_studio(str(self.pdf), output_dir=self.root / 'out')
        self.assertNotEqual(first['directory'], second['directory'])
        self.assertTrue((Path(first['directory']) / 'business_input.pdf').exists())
