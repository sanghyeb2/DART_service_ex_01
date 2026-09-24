"""PDF의 키워드 관련 페이지와 주변 페이지를 Agent 입력으로 만든다."""

import logging
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unicodedata
from uuid import uuid4

import pymupdf

from config import BASE_DIR, MAX_INPUT_CHARS

logger = logging.getLogger(__name__)

BUSINESS_KEYWORDS = [
    '사업의 내용', '사업의 개요', '주요 제품', '주요 서비스', '시장', '산업',
    '경쟁', '매출', '판매', '위험관리', '위험 요인',
]
TECH_KEYWORDS = [
    '연구개발', 'R&D', '연구 개발', '설비투자', '시설투자', '생산설비',
    '생산능력', '가동률', '신규사업', '신사업', '직원 현황', '직원', '임직원',
]


class PDFProcessingError(ValueError):
    """화면에 표시할 수 있는 PDF 처리 오류."""


def extract_pages_from_pdf(pdf_path: str) -> list[dict]:
    path = Path(pdf_path)
    if path.suffix.lower() != '.pdf':
        raise PDFProcessingError('PDF 파일을 선택해주세요.')
    try:
        if path.stat().st_size == 0:
            raise PDFProcessingError('빈 파일입니다. 내용이 있는 PDF를 업로드해주세요.')
        with pymupdf.open(path) as document:
            if not document.is_pdf:
                raise PDFProcessingError('올바른 PDF 파일이 아닙니다.')
            if document.needs_pass:
                raise PDFProcessingError('암호로 보호된 PDF입니다. 암호를 해제한 후 업로드해주세요.')
            pages = [{'page': i + 1, 'text': page.get_text('text', sort=True).strip()}
                     for i, page in enumerate(document)]
        if not pages or not any(page['text'] for page in pages):
            raise PDFProcessingError(
                'PDF에서 텍스트를 추출할 수 없습니다. 스캔본 대신 텍스트를 선택할 수 있는 PDF를 사용해주세요.'
            )
        return pages
    except PDFProcessingError:
        raise
    except Exception as exc:
        logger.exception('PDF text extraction failed')
        raise PDFProcessingError('PDF를 읽지 못했습니다. 파일이 손상되지 않았는지 확인해주세요.') from exc


def select_pages_by_keywords(
    pages: list[dict], keywords: list[str], context_pages: int = 1,
) -> list[dict]:
    if context_pages < 0:
        raise ValueError('context_pages는 0 이상이어야 합니다.')
    # PDF에서 한글 사이에 생긴 공백/줄바꿈, R&D의 대소문자 차이를 허용한다.
    normalize = lambda value: re.sub(r'\s+', '', value).casefold()
    needles = [normalize(word) for word in keywords if word.strip()]
    ordered = sorted({p['page']: p for p in pages}.values(), key=lambda p: p['page'])
    selected = set()
    for index, page in enumerate(ordered):
        if any(word in normalize(page['text']) for word in needles):
            selected.update(range(max(0, index - context_pages),
                                  min(len(ordered), index + context_pages + 1)))
    return [ordered[index] for index in sorted(selected)]


def build_text_with_page_markers(pages: list[dict]) -> str:
    return '\n\n'.join(f"===== PAGE {page['page']} =====\n{page['text']}" for page in pages)


def _limited_text(pages: list[dict], limit: int) -> tuple[str, bool]:
    """본문만 자를 수 있으며 불완전한 페이지 마커를 만들지 않는다."""
    parts = []
    used = 0
    for page in pages:
        prefix = ('\n\n' if parts else '') + f"===== PAGE {page['page']} =====\n"
        available = limit - used - len(prefix)
        if available <= 0:
            return ''.join(parts), True
        text = page['text']
        part = prefix + text[:available]
        parts.append(part)
        used += len(part)
        if len(text) > available:
            return ''.join(parts), True
    return ''.join(parts), False


def _compact(text: str) -> str:
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text)).casefold()


def _sections(pdf_path: str, pages: list[dict]) -> tuple[list[dict], str]:
    """PDF 책갈피 우선, 없으면 페이지 상단의 장/절 제목을 사용한다."""
    toc = []
    if Path(pdf_path).is_file():
        with pymupdf.open(pdf_path) as doc:
            toc = [row for row in doc.get_toc() if 1 <= row[2] <= len(pages)]
    method = 'pdf_bookmarks'
    if not any('사업의내용' in _compact(row[1]) for row in toc):
        toc = []
        method = 'text_headings'
        for page in pages:
            lines = [line.strip() for line in page['text'].splitlines() if line.strip()]
            for line in lines[:8]:
                # 인쇄 목차의 점선/페이지 숫자와 본문의 소수점 숫자를 제목으로 오인하지 않는다.
                normalized = unicodedata.normalize('NFKC', line)
                if len(normalized) > 80 or re.search(r'\.{2,}|…|\d\s*$', normalized):
                    continue
                if re.match(r'^[IVX]+\.\s*[가-힣]', normalized):
                    toc.append([1, line, page['page']])
                elif re.match(r'^\d{1,2}\.\s*[가-힣]', normalized):
                    toc.append([2, line, page['page']])
                elif _compact(line) == '반기보고서':
                    toc.append([1, line, page['page']])
    sections = []
    for index, (level, title, start) in enumerate(toc):
        end = len(pages)
        for next_level, _, next_start in toc[index + 1:]:
            if next_level <= level:
                end = max(start, next_start - 1)
                break
        sections.append({'title': title, 'level': level, 'start': start, 'end': end})
    return sections, method


def _select_report_pages(pdf_path: str, pages: list[dict]) -> dict:
    sections, method = _sections(pdf_path, pages)
    business_sections = [s for s in sections if s['level'] == 1 and '사업의내용' in _compact(s['title'])]
    if not business_sections:
        return {
            'business': select_pages_by_keywords(pages, BUSINESS_KEYWORDS),
            'tech': select_pages_by_keywords(pages, TECH_KEYWORDS),
            'selection_method': 'keywords',
            'warnings': ['사업의 내용 구간을 식별하지 못해 키워드와 앞뒤 1페이지로 선별했습니다. 포함 페이지를 확인해주세요.'],
        }

    def section_numbers(section):
        return set(range(section['start'], section['end'] + 1))

    business_numbers = set().union(*(section_numbers(s) for s in business_sections))
    overview_chapters = [s for s in sections if s['level'] == 1
                         and re.sub(r'^[ivx]+\.', '', _compact(s['title'])) == '회사의개요']
    shared = set()
    for section in sections:
        title = _compact(section['title'])
        if title == '반기보고서':
            shared.add(section['start'])
        elif (section['level'] > 1 and re.sub(r'^\d+\.', '', title) == '회사의개요'
              and any(chapter['start'] <= section['start'] <= chapter['end']
                      for chapter in overview_chapters)):
            shared.update(section_numbers(section))

    tech_numbers = set()
    # 표가 다음 페이지로 이어져도 연구개발/설비 절 전체를 유지한다.
    tech_titles = ('사업의개요', '주요제품', '주요서비스', '연구개발', '생산설비',
                   '설비투자', '시설투자', '신규사업', '신사업', '요약재무정보')
    for section in sections:
        if section['level'] > 1 and any(word in _compact(section['title']) for word in tech_titles):
            tech_numbers.update(section_numbers(section))
    in_business = [p for p in pages if p['page'] in business_numbers]
    tech_numbers.update(p['page'] for p in select_pages_by_keywords(in_business, TECH_KEYWORDS))

    # 임원 명단 전체 대신 '직원 현황'부터 해당 절의 끝까지 포함한다.
    employee_sections = [s for s in sections if s['level'] > 1 and '직원' in _compact(s['title'])]
    employee_found = False
    for section in employee_sections:
        candidates = [p for p in pages if section['start'] <= p['page'] <= section['end']]
        matches = [p['page'] for p in candidates if '직원현황' in _compact(p['text'])]
        if matches:
            tech_numbers.update(range(max(section['start'], min(matches) - 1), section['end'] + 1))
            employee_found = True
    warnings = []
    if not employee_found:
        # 장/절 제목이 다른 문서는 명확한 직원 현황 표제만으로 보완한다.
        employees = select_pages_by_keywords(pages, ['직원 현황', '직원현황'])
        tech_numbers.update(p['page'] for p in employees)
        if not employees:
            warnings.append('직원 현황 페이지를 식별하지 못했습니다. 원본 보고서와 선별 결과를 확인해주세요.')
    return {
        'business': [p for p in pages if p['page'] in business_numbers | shared],
        'tech': [p for p in pages if p['page'] in tech_numbers | shared],
        'selection_method': method, 'warnings': warnings,
    }


def preprocess_report(pdf_path: str, *, max_input_chars: int = MAX_INPUT_CHARS) -> dict:
    if max_input_chars < 64:
        raise ValueError('최대 입력 길이는 64자 이상이어야 합니다.')
    pages = extract_pages_from_pdf(pdf_path)
    selection = _select_report_pages(pdf_path, pages)
    result = {'all_pages': pages, 'warnings': list(selection['warnings']),
              'selection_method': selection['selection_method']}
    blank_pages = [p['page'] for p in pages if not p['text']]
    if blank_pages:
        result['warnings'].append(
            f'텍스트가 없는 {len(blank_pages)}개 페이지가 있습니다. 이미지·스캔 내용은 분석하지 않습니다.'
        )
    for key, label in (('business', 'Business'), ('tech', 'Tech')):
        selected = selection[key]
        text, truncated = _limited_text(selected, max_input_chars)
        result[f'{key}_text'] = text
        result[f'{key}_pages'] = [p['page'] for p in selected]
        if not selected:
            result['warnings'].append(f'{label} 키워드와 일치하는 페이지가 없습니다.')
        if truncated:
            result['warnings'].append(
                f'{label} 입력이 {max_input_chars:,}자 한도로 잘렸습니다. 뒷부분은 포함되지 않습니다.'
            )
    return result


def export_report_for_studio(
    pdf_path: str, *, output_dir: Path | None = None, source_name: str | None = None,
) -> dict:
    """선별 페이지 전체를 원문 배치의 PDF 2개로 저장한다. 글자 수로 자르지 않는다."""
    pages = extract_pages_from_pdf(pdf_path)
    selection = _select_report_pages(pdf_path, pages)
    for key in ('business', 'tech'):
        if not selection[key]:
            raise PDFProcessingError(f'{key}용 페이지를 선별하지 못했습니다. 반기보고서 PDF인지 확인해주세요.')
    warnings = list(selection['warnings'])
    if any(not p['text'] for p in pages):
        warnings.append('텍스트가 없는 페이지가 있습니다. 선택된 페이지의 이미지/표는 PDF에 보존되지만 OCR은 수행하지 않았습니다.')
    source_path = Path(pdf_path)
    manifest = {
        'source_filename': source_name or source_path.name,
        'source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
        'source_page_count': len(pages), 'selection_method': selection['selection_method'],
        'page_number_rule': 'source_page는 SOURCE PDF PAGE에 표시된 원본 PDF의 1-based 물리적 페이지 번호',
        'text_truncated': False, 'warnings': warnings, 'files': {},
    }
    root = Path(output_dir) if output_dir is not None else BASE_DIR / 'output' / 'studio_inputs'
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f'report-{uuid4().hex[:12]}'
    # 새 디렉터리를 완성한 뒤 공개한다. 이전 실행의 PDF와 섞이지 않는다.
    with tempfile.TemporaryDirectory(prefix='.preparing-', dir=root) as temporary:
        staging = Path(temporary)
        with pymupdf.open(source_path) as source:
            for key in ('business', 'tech'):
                selected = selection[key]
                filename = f'{key}_input.pdf'
                with pymupdf.open() as target:
                    for index, selected_page in enumerate(selected, 1):
                        number = selected_page['page']
                        original = source[number - 1]
                        # 위쪽에 별도 여백을 만든다. 본문 영역은 가리지 않고 원래 크기를 유지한다.
                        width, height = original.rect.width, original.rect.height
                        page = target.new_page(width=width, height=height + 28)
                        if original.get_contents():
                            page.show_pdf_page(pymupdf.Rect(0, 28, width, height + 28), source, number - 1)
                        page.insert_text((12, 17),
                                         f'SOURCE PDF PAGE {number} | {key.upper()} | FILE PAGE {index}',
                                         fontsize=8, color=(0.12, 0.25, 0.42))
                    target.set_metadata({'title': f'{key.title()} input - {source_path.stem}',
                                         'subject': 'Selected source pages for Studio agent setup'})
                    target.save(staging / filename, garbage=4, deflate=True)
                manifest['files'][key] = {
                    'filename': filename,
                    'page_count': len(selected),
                    'source_pages': [p['page'] for p in selected],
                    'extracted_text_chars': len(build_text_with_page_markers(selected)),
                    'page_map': [{'file_page': i, 'source_page': p['page']}
                                 for i, p in enumerate(selected, 1)],
                }
        (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        staging.rename(destination)
    return {'directory': str(destination), 'manifest': manifest}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='반기보고서에서 Studio 업로드용 Business/Tech PDF를 생성합니다.')
    parser.add_argument('pdf_path', help='원본 반기보고서 PDF 경로')
    parser.add_argument('--output-dir', type=Path, help='결과 디렉터리의 상위 경로')
    args = parser.parse_args()
    try:
        result = export_report_for_studio(args.pdf_path, output_dir=args.output_dir)
    except (PDFProcessingError, OSError) as exc:
        parser.exit(1, f'전처리 실패: {exc}\n')
    print('저장 위치:', result['directory'])
    for key, item in result['manifest']['files'].items():
        print(f"{key}: {item['filename']} / {item['page_count']}페이지 / {item['extracted_text_chars']:,}자")
    for warning in result['manifest']['warnings']:
        print('안내:', warning)
