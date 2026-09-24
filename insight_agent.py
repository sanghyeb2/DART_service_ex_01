"""두 Extract JSON만 사용하는 Insight Agent. Mock에서는 단순 템플릿으로 조합한다."""

from agent_client import run_agent_with_json
from config import Settings
from schemas import BusinessResult, TechResult, InsightResult

INSIGHT_RULES = '''
1. 입력 JSON에 없는 사실을 새로 생성하지 않는다.
2. 기업이 특정 직무를 실제 채용 중이라고 단정하지 않는다.
3. R&D, 투자, 제품, 사업전략을 근거로 관련성이 높은 직무/기술 영역을 제시한다.
4. 모든 핵심 인사이트는 가능한 경우 evidence를 포함한다.
5. 지나친 투자추천, 기업평가, 미래 실적예측은 하지 않는다.
6. 문서에서 확인되지 않는 정보는 "확인되지 않음"으로 처리한다.
'''.strip()


def _fact_item(description: str, source_page: int | None) -> dict:
    return {'description': description,
            'evidence': [{'fact': description, 'source_page': source_page}]}


def _mock_insight(business: dict, tech: dict) -> dict:
    result = InsightResult().model_dump()
    result['industry_trends'] = [_fact_item(x['description'], x['source_page'])
                                 for x in business['market_conditions']]
    result['company_strategy'] = [_fact_item(x, None) for x in business['sales_strategy']]
    result['technology_focus'] = [_fact_item(x['description'], x['source_page'])
                                  for x in tech['rd_projects']]
    result['investment_direction'] = [_fact_item(f"{x['target']}: {x['purpose']}", x['source_page'])
                                      for x in tech['major_investments']]
    result['risk_signals'] = [_fact_item(x['description'], x['source_page'])
                              for x in business['major_risks']]
    # 투자/연구개발이 있다는 이유만으로 미래 성장을 단정하지 않는다.
    for project in tech['rd_projects']:
        if not project['description']:
            continue
        result['job_insights'].append({
            'job_area': f"{project['technology'] or project['project_name']} 관련 연구개발",
            'reason': '해당 연구개발 내용과 관련된 기술 영역입니다. 실제 채용 여부는 확인되지 않음.',
            'keywords': [project['technology']] if project['technology'] else [],
            'evidence': [{'fact': project['description'], 'source_page': project['source_page']}],
        })
        result['interview_points'].append(
            f"'{project['project_name']}'의 기술적 과제와 본인의 관련 경험을 연결해 설명해보세요."
        )
    result['job_keywords'] = list(tech['technology_keywords'])
    result['summary'] = business['business_summary'] or '기업 전략은 입력 JSON에서 확인되지 않음.'
    return result


def generate_insight(business_result: dict, tech_result: dict) -> dict:
    business = BusinessResult.model_validate(business_result).model_dump()
    tech = TechResult.model_validate(tech_result).model_dump()
    settings = Settings.from_env()
    result = _mock_insight(business, tech) if settings.use_mock else run_agent_with_json(
        settings.insight_agent_id, {'business': business, 'technology_and_investment': tech},
    )
    return InsightResult.model_validate(result).model_dump()
