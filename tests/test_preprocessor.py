from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from preprocessor import (
    PDFProcessingError, extract_pages_from_pdf, select_pages_by_keywords,
    build_text_with_page_markers, preprocess_report,
)


class PreprocessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'report.pdf'
        log = patch('preprocessor.logger')
        log.start()
        self.addCleanup(log.stop)

    def pdf(self, texts, **save_options):
        with pymupdf.open() as doc:
            for text in texts:
                page = doc.new_page()
                page.insert_text((50, 60), text, fontname='korea')
            doc.save(self.path, **save_options)
        return str(self.path)

    def test_real_pdf_preserves_one_based_pages_and_korean(self):
        pages = extract_pages_from_pdf(self.pdf(['사업의 내용', '연구개발 R&D']))
        self.assertEqual([p['page'] for p in pages], [1, 2])
        self.assertIn('사업의 내용', pages[0]['text'])

    def test_context_deduplicates_and_handles_document_boundaries(self):
        pages = [{'page': i, 'text': '시장' if i in (1, 3, 5) else '본문'} for i in range(1, 6)]
        self.assertEqual(select_pages_by_keywords(pages, ['시장']), pages)
        self.assertEqual([p['page'] for p in select_pages_by_keywords(pages, ['시장'], 0)], [1, 3, 5])

    def test_spaces_and_case_and_no_matches(self):
        pages = [{'page': 1, 'text': '연구\n개발 r&d'}, {'page': 2, 'text': '본문'}]
        self.assertEqual(select_pages_by_keywords(pages, ['연구개발'], 0), pages[:1])
        self.assertEqual(select_pages_by_keywords(pages, ['R&D'], 0), pages[:1])
        self.assertEqual(select_pages_by_keywords(pages, ['없는키워드']), [])

    def test_markers_and_length_limit(self):
        pages = [{'page': 1, 'text': '시장' * 100}, {'page': 2, 'text': 'R&D' * 100}]
        self.assertIn('===== PAGE 2 =====', build_text_with_page_markers(pages))
        with patch('preprocessor.extract_pages_from_pdf', return_value=pages):
            result = preprocess_report('test.pdf', max_input_chars=90)
        for key in ('business_text', 'tech_text'):
            self.assertLessEqual(len(result[key]), 90)
            self.assertTrue(result[key].startswith('===== PAGE 1 =====\n'))
        self.assertTrue(result['warnings'])

    def test_no_keywords_and_partial_blank_page_are_reported(self):
        result = preprocess_report(self.pdf(['Unrelated text', '']))
        self.assertEqual(result['business_text'], '')
        self.assertEqual(result['tech_text'], '')
        self.assertGreaterEqual(len(result['warnings']), 3)

    def test_invalid_empty_and_scan_only_pdf(self):
        for contents in (b'', b'not a pdf', b'%PDF-1.7\ninvalid'):
            self.path.write_bytes(contents)
            with self.assertRaises(PDFProcessingError):
                extract_pages_from_pdf(str(self.path))
        with self.assertRaisesRegex(PDFProcessingError, '텍스트'):
            extract_pages_from_pdf(self.pdf(['']))

    def test_non_pdf_and_missing_path(self):
        with self.assertRaises(PDFProcessingError):
            extract_pages_from_pdf(str(self.path))
        other = self.path.with_suffix('.txt')
        other.write_text('hello')
        with self.assertRaises(PDFProcessingError):
            extract_pages_from_pdf(str(other))

    def test_encrypted_pdf(self):
        path = self.pdf(['secret'], encryption=pymupdf.PDF_ENCRYPT_AES_256,
                        owner_pw='owner', user_pw='user')
        with self.assertRaisesRegex(PDFProcessingError, '암호'):
            extract_pages_from_pdf(path)


if __name__ == '__main__':
    unittest.main()
