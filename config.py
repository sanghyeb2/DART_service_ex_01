"""환경변수는 실행 시 읽는다. 기본값은 외부 API를 쓰지 않는 Mock이다."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
MAX_INPUT_CHARS = 120_000


@dataclass(frozen=True)
class Settings:
    use_mock: bool = True
    upstage_api_key: str = ''
    business_agent_id: str = ''
    tech_agent_id: str = ''
    insight_agent_id: str = ''
    upstage_agent_api_url: str = ''

    @classmethod
    def from_env(cls):
        load_dotenv(BASE_DIR / '.env', override=False)
        mode = os.getenv('USE_MOCK', 'true').strip().lower()
        if mode not in ('true', 'false'):
            raise ValueError('USE_MOCK은 true 또는 false로 설정해주세요.')
        names = ('upstage_api_key', 'business_agent_id', 'tech_agent_id',
                 'insight_agent_id', 'upstage_agent_api_url')
        return cls(use_mock=mode == 'true', **{
            name: os.getenv(name.upper(), '').strip() for name in names
        })
