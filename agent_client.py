"""Studio API 통신의 유일한 진입점. 실제 연결은 후속 Phase 3에서 구현한다."""

import json

from config import Settings


class AgentError(RuntimeError):
    """화면에 표시할 수 있는 Agent 설정/호출 오류."""


def run_agent(agent_id: str, input_text: str) -> dict:
    settings = Settings.from_env()
    required = {'UPSTAGE_API_KEY': settings.upstage_api_key,
                'Agent ID': agent_id, 'UPSTAGE_AGENT_API_URL': settings.upstage_agent_api_url}
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise AgentError('Agent 설정이 필요합니다: ' + ', '.join(missing)
                         + '. 로컬 테스트는 USE_MOCK=true로 실행해주세요.')
    # 미확인 API 형식을 추측해 요청하지 않는다. 연결은 이 함수 내부에서만 추가한다.
    raise AgentError('실제 Studio API 연결은 Phase 3에서 구현합니다. USE_MOCK=true로 실행해주세요.')


def run_agent_with_json(agent_id: str, payload: dict) -> dict:
    return run_agent(agent_id, json.dumps(payload, ensure_ascii=False, allow_nan=False))
