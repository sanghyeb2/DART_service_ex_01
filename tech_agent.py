"""Tech & Investment Extract. Mock 수치와 근거는 가상 샘플의 예시다."""

from agent_client import run_agent
from config import Settings
from schemas import TechResult

MOCK_TECH_RESULT = {
    'revenue': '1,000억 원 (가상)',
    'operating_profit': '80억 원 (가상)',
    'rd_expense': '50억 원 (가상)',
    'rd_focus': ['배터리 상태 추정', '배터리 안전성'],
    'rd_projects': [{'project_name': '배터리 SOH 추정', 'technology': 'Battery Modeling',
                     'description': '배터리 수명 상태를 추정하는 모델을 개발한다.', 'source_page': 3}],
    'major_investments': [{'target': '배터리 시험설비', 'amount': '20억 원 (가상)',
                           'purpose': '배터리 안전성 검증', 'status': '구축 중', 'source_page': 3}],
    'production_status': [{'site': '가상 제1공장', 'capacity': '연 10만 개', 'output': '반기 4만 개',
                           'utilization': '80%', 'source_page': 3}],
    'new_business': ['배터리 진단 소프트웨어'],
    'employee_count': 120,
    'employee_summary': '가상 기업의 직원 수 예시이며 실제 채용 현황은 확인되지 않음.',
    'technology_keywords': ['BMS', 'SOH', 'Battery Modeling'],
}


def analyze_technology_and_investment(text: str) -> dict:
    settings = Settings.from_env()
    result = MOCK_TECH_RESULT if settings.use_mock else run_agent(settings.tech_agent_id, text)
    return TechResult.model_validate(result).model_dump()
