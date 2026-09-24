"""PDF 업로드 → 전처리 → Extract 2개 → Insight → Streamlit 5개 탭."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import tempfile

from pydantic import ValidationError
import streamlit as st

from agent_client import AgentError
from business_agent import analyze_business
from config import BASE_DIR, Settings
from insight_agent import generate_insight
from preprocessor import PDFProcessingError, preprocess_report, export_report_for_studio
from tech_agent import analyze_technology_and_investment

logger = logging.getLogger(__name__)
TAB_NAMES = ['기업 개요', '산업 동향', '기술 & 투자', '취업 인사이트', '근거 / 원문']


def analyze_report(pdf_path: str, *, output_dir: Path | None = None) -> dict:
    """두 Extract를 병렬 실행하고, 모두 성공한 뒤 Insight와 저장을 진행한다."""
    settings = Settings.from_env()
    prepared = preprocess_report(pdf_path)
    # PDF 처리와 Streamlit UI는 주 스레드에 두고 독립적인 Agent 호출만 병렬화한다.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='dart-extract') as executor:
        business_future = executor.submit(analyze_business, prepared['business_text'])
        tech_future = executor.submit(analyze_technology_and_investment, prepared['tech_text'])
        business = business_future.result()
        tech = tech_future.result()
    insight = generate_insight(business, tech)
    destination = Path(output_dir) if output_dir is not None else BASE_DIR / 'output'
    destination.mkdir(parents=True, exist_ok=True)
    # 직렬화/쓰기 실패가 기존 결과 파일을 곧바로 손상시키지 않게 임시 파일을 사용한다.
    with tempfile.TemporaryDirectory(prefix='.analysis-', dir=destination) as temporary:
        staging = Path(temporary)
        for key in ('business', 'tech'):
            (staging / f'{key}_input.txt').write_text(prepared[f'{key}_text'], encoding='utf-8')
        for key, value in (('business', business), ('tech', tech), ('insight', insight)):
            (staging / f'{key}_result.json').write_text(
                json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8',
            )
        files = list(staging.iterdir())
        previous = staging / 'previous'
        previous.mkdir()
        for path in files:
            target = destination / path.name
            if target.exists():
                (previous / path.name).write_bytes(target.read_bytes())
        replaced = []
        try:
            for path in files:
                path.replace(destination / path.name)
                replaced.append(path.name)
        except OSError:
            # Windows에서 뒤쪽 결과 파일이 잠겨 있어도 앞서 바꾼 파일을 복원한다.
            for name in reversed(replaced):
                old = previous / name
                if old.exists():
                    old.replace(destination / name)
                else:
                    (destination / name).unlink()
            raise
    return {'business': business, 'tech': tech, 'insight': insight,
            'preprocessed': prepared, 'is_mock': settings.use_mock}


def clear_result():
    st.session_state.pop('analysis_result', None)
    st.session_state.pop('source_page', None)
    st.session_state.pop('studio_export', None)


def render_studio_preparation(uploaded, content):
    st.subheader('Studio Agent 생성용 PDF 준비')
    st.caption('원문 표와 배치를 유지한 Business·Tech PDF를 만듭니다. Agent 호출 없이 실행하며 120,000자 제한으로 자르지 않습니다.')
    if st.button('Studio용 PDF 만들기', key='prepare_studio'):
        clear_result()
        if uploaded is None:
            st.info('반기보고서 PDF를 먼저 업로드해주세요.')
        else:
            try:
                if Path(uploaded.name).suffix.lower() != '.pdf':
                    raise PDFProcessingError('PDF 파일을 선택해주세요.')
                with st.spinner('Studio에 올릴 PDF를 준비하고 있습니다...'):
                    with tempfile.TemporaryDirectory(prefix='dart-studio-') as temporary:
                        path = Path(temporary) / 'report.pdf'
                        path.write_bytes(content)
                        st.session_state['studio_export'] = export_report_for_studio(
                            str(path), output_dir=BASE_DIR / 'output' / 'studio_inputs',
                            source_name=uploaded.name,
                        )
            except PDFProcessingError as exc:
                logger.exception('Studio PDF preparation failed')
                st.error(str(exc))
            except Exception:
                logger.exception('Could not export Studio PDFs')
                st.error('Studio용 PDF를 만들지 못했습니다. 원본 파일과 output 폴더의 접근 권한을 확인해주세요.')
    exported = st.session_state.get('studio_export')
    if not exported:
        return
    manifest = exported['manifest']
    directory = Path(exported['directory'])
    st.success('Studio 업로드용 PDF를 생성했습니다. 아래 파일로 Extract Agent를 각각 만드세요.')
    for key, label in (('business', 'Business'), ('tech', 'Tech & Investment')):
        item = manifest['files'][key]
        st.write(f"{label}: 원본 {manifest['source_page_count']}페이지 중 {item['page_count']}페이지 선별")
        st.download_button(f'{label} PDF 내려받기', (directory / item['filename']).read_bytes(),
                           file_name=item['filename'], mime='application/pdf', key=f'download_{key}')
    st.caption('source_page에는 PDF 상단의 SOURCE PDF PAGE 숫자를 사용하세요. 새 파일의 페이지 순서와 다를 수 있습니다.')
    st.caption(f'로컬 저장 위치: {directory}')
    for warning in manifest['warnings']:
        st.warning(warning)
    st.download_button('원본 페이지 대응표 내려받기', (directory / 'manifest.json').read_bytes(),
                       file_name='manifest.json', mime='application/json', key='download_manifest')


def display_value(value) -> str:
    return '-' if value is None or value == '' else str(value)


def render_items(title: str, items):
    st.subheader(title)
    if not isinstance(items, list) or not items:
        st.caption('확인되지 않음')
        return
    for item in items:
        if isinstance(item, str):
            st.write('• ' + item)
        elif isinstance(item, dict):
            with st.container(border=True):
                labels = {
                    'topic': '주제', 'risk': '위험', 'description': '내용',
                    'project_name': '프로젝트', 'technology': '기술',
                    'target': '투자 대상', 'amount': '금액', 'purpose': '목적', 'status': '진행 상태',
                    'site': '사업장', 'capacity': '생산능력', 'output': '생산량', 'utilization': '가동률',
                    'job_area': '관련 직무 영역', 'reason': '관련 이유',
                }
                for key, label in labels.items():
                    if item.get(key):
                        st.write(f'{label}: {item[key]}')
                if isinstance(item.get('keywords'), list):
                    st.write('기술 키워드: ' + ', '.join(str(x) for x in item['keywords']))
                if item.get('source_page'):
                    st.caption(f"출처 페이지: {item['source_page']}")
                for evidence in item.get('evidence', []):
                    if isinstance(evidence, dict):
                        st.caption(f"근거: {evidence.get('fact', '')} · 페이지 {display_value(evidence.get('source_page'))}")


def evidence_rows(business: dict, tech: dict) -> list[dict]:
    rows = []
    groups = [(business, 'market_conditions', '시장'), (business, 'market_outlook', '전망'),
              (business, 'major_risks', '위험'), (tech, 'rd_projects', 'R&D'),
              (tech, 'major_investments', '투자'), (tech, 'production_status', '생산')]
    for result, key, label in groups:
        items = result.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and type(item.get('source_page')) is int and item['source_page'] > 0:
                fact = ' · '.join(str(value) for name, value in item.items()
                                  if name != 'source_page' and value not in ('', None))
                rows.append({'구분': label, 'Fact': fact, 'Page': item['source_page']})
    return rows


def render_results(result):
    tabs = st.tabs(TAB_NAMES)
    if result is None:
        for tab in tabs:
            with tab:
                st.info('PDF를 업로드하고 기업 분석하기를 눌러주세요.')
        return
    business, tech, insight = result['business'], result['tech'], result['insight']
    with tabs[0]:
        st.subheader(business.get('company_name') or '기업명 확인되지 않음')
        st.caption('보고기간: ' + display_value(business.get('report_period')))
        st.write(business.get('business_summary') or '사업 요약 확인되지 않음')
        columns = st.columns(3)
        for column, label, key in zip(columns, ['매출', '영업이익', '직원 수'],
                                      ['revenue', 'operating_profit', 'employee_count']):
            column.metric(label, display_value(tech.get(key)))
        render_items('주요 사업부문', business.get('business_segments'))
        render_items('주요 제품', business.get('major_products'))
        st.caption(tech.get('employee_summary') or '직원 현황 확인되지 않음')
    with tabs[1]:
        for title, key in [('시장 현황', 'market_conditions'), ('시장 전망', 'market_outlook'),
                           ('경쟁 요인', 'competitive_factors'), ('판매 전략', 'sales_strategy'),
                           ('주요 위험', 'major_risks')]:
            render_items(title, business.get(key))
        render_items('산업 인사이트', insight.get('industry_trends'))
    with tabs[2]:
        st.metric('연구개발비', display_value(tech.get('rd_expense')))
        for title, key in [('R&D 중점 분야', 'rd_focus'), ('R&D 프로젝트', 'rd_projects'),
                           ('주요 투자', 'major_investments'), ('생산 현황', 'production_status'),
                           ('신사업', 'new_business'), ('기술 키워드', 'technology_keywords')]:
            render_items(title, tech.get(key))
        for title, key in [('기술 방향', 'technology_focus'), ('투자 방향', 'investment_direction'),
                           ('성장 신호', 'growth_signals'), ('위험 신호', 'risk_signals')]:
            render_items(title, insight.get(key))
    with tabs[3]:
        st.info('연구개발·사업 내용과 관련된 직무/기술 영역입니다. 실제 채용 여부는 확인되지 않음.')
        render_items('관련 직무 영역과 근거', insight.get('job_insights'))
        render_items('직무 기술 키워드', insight.get('job_keywords'))
        render_items('면접 활용 포인트', insight.get('interview_points'))
        render_items('기업 전략', insight.get('company_strategy'))
        st.subheader('기업 전략 요약')
        st.write(insight.get('summary') or '확인되지 않음')
    with tabs[4]:
        st.subheader('Extract 결과의 근거')
        if result['is_mock']:
            st.warning('아래 Fact와 Page는 가상 Mock 예시의 근거입니다. 업로드한 PDF의 근거가 아닙니다.')
        rows = evidence_rows(business, tech)
        if rows:
            st.dataframe(rows, hide_index=True, width='stretch')
        else:
            st.caption('페이지 근거가 있는 항목이 없습니다.')
        st.subheader('업로드한 PDF의 실제 원문')
        pages = result['preprocessed']['all_pages']
        page_number = st.selectbox('PDF 페이지 번호', [p['page'] for p in pages], key='source_page')
        st.text(next(p['text'] for p in pages if p['page'] == page_number) or '(추출된 텍스트 없음)')
        with st.expander('Agent 입력으로 선별한 텍스트'):
            st.caption('페이지 번호는 PDF 파일의 물리적 페이지 번호입니다.')
            st.text(result['preprocessed']['business_text'] or '(Business 선별 페이지 없음)')
            st.text(result['preprocessed']['tech_text'] or '(Tech 선별 페이지 없음)')
        with st.expander('Agent 결과 JSON'):
            st.json({'business': business, 'technology_and_investment': tech, 'insight': insight})


def main():
    st.set_page_config(page_title='DART Insight AI', layout='wide')
    st.title('DART Insight AI')
    st.write('DART 반기보고서를 기반으로 기업·산업·기술·취업 인사이트를 제공합니다.')
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        clear_result()
        st.error(str(exc))
        render_results(None)
        return
    if settings.use_mock:
        st.warning('Mock 모드: 기업 분석하기 결과는 가상 기업의 예시입니다. '
                   'Studio용 PDF 만들기는 업로드한 실제 원문으로 동작합니다.')
    else:
        st.info('실제 Studio 연결은 Phase 3 작업입니다. 현재 테스트는 USE_MOCK=true를 사용해주세요.')
    uploaded = st.file_uploader('반기보고서 PDF 업로드', type=['pdf'], on_change=clear_result)
    content = uploaded.getvalue() if uploaded is not None else None
    signature = (hashlib.sha256(content).hexdigest(), uploaded.name, settings.use_mock) if content is not None else None
    if st.session_state.get('upload_signature') != signature:
        clear_result()
        st.session_state['upload_signature'] = signature
    if st.button('기업 분석하기', type='primary'):
        clear_result()
        if uploaded is None:
            st.info('반기보고서 PDF를 먼저 업로드해주세요.')
        else:
            try:
                if Path(uploaded.name).suffix.lower() != '.pdf':
                    raise PDFProcessingError('PDF 파일을 선택해주세요.')
                with st.spinner('반기보고서를 분석하고 있습니다...'):
                    # 사용자 파일명으로 디스크 경로를 만들지 않는다. 임시 업로드는 항상 정리된다.
                    with tempfile.TemporaryDirectory(prefix='dart-upload-') as temporary:
                        path = Path(temporary) / 'report.pdf'
                        path.write_bytes(content)
                        st.session_state['analysis_result'] = analyze_report(str(path))
            except (PDFProcessingError, AgentError) as exc:
                logger.exception('Report analysis failed')
                st.error(str(exc))
            except ValidationError:
                logger.exception('Agent returned an invalid schema')
                st.error('Agent 결과 형식이 올바르지 않습니다. Agent의 JSON 스키마를 확인해주세요.')
            except OSError:
                logger.exception('Could not read or save analysis files')
                st.error('파일을 읽거나 결과를 저장하지 못했습니다. 파일과 output 폴더의 접근 권한을 확인해주세요.')
            except Exception:
                logger.exception('Unexpected analysis error')
                st.error('분석 중 오류가 발생했습니다. 환경변수와 Agent 설정을 확인하고 다시 시도해주세요.')
    render_studio_preparation(uploaded, content)
    result = st.session_state.get('analysis_result')
    if result:
        st.success('Mock 파이프라인 실행 완료' if result['is_mock'] else '분석 완료')
        st.caption('output 폴더에 선별 텍스트 2개와 결과 JSON 3개를 저장했습니다. 최신 성공 실행으로 덮어씁니다.')
        for warning in result['preprocessed']['warnings']:
            st.warning(warning)
    render_results(result)


if __name__ == '__main__':
    main()
