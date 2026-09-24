"""Business Extract: Mock 예시 또는 Studio 응답을 README 스키마로 검증한다."""

from agent_client import run_agent
from config import Settings
from schemas import BusinessResult

MOCK_BUSINESS_RESULT = {
    'company_name': '가상 모빌리티 (Mock 예시)',
    'report_period': '2026 반기 (가상 예시)',
    'business_summary': '전기차 부품과 배터리 관리 소프트웨어를 개발하는 가상 기업입니다.',
    'business_segments': ['전기차 부품', '배터리 소프트웨어'],
    'major_products': ['배터리 관리 시스템(BMS)', '전동화 부품'],
    'market_conditions': [{'topic': '전기차 부품 시장',
                           'description': '고객사가 배터리 효율과 안전성을 요구하고 있다.', 'source_page': 2}],
    'market_outlook': [{'topic': '시장 전망',
                       'description': '보고서는 충전 인프라 보급 속도를 수요 변수로 제시한다.', 'source_page': 2}],
    'competitive_factors': ['배터리 상태 추정 기술', '고객사 공동 개발'],
    'sales_strategy': ['고객사와 공동 검증 후 부품 공급'],
    'major_risks': [{'risk': '원재료 가격', 'description': '원재료 가격 변동이 원가에 영향을 준다.',
                     'source_page': 2}],
}


def analyze_business(text: str) -> dict:
    settings = Settings.from_env()
    result = MOCK_BUSINESS_RESULT if settings.use_mock else run_agent(settings.business_agent_id, text)
    return BusinessResult.model_validate(result).model_dump()
