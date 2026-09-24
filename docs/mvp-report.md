# README Phase 1 + 2 작업 보고

> 이 문서는 초기 구현과 Studio PDF 준비의 이력이다. 2026-09-25 확정 기획에 맞춘 현재 상태와 병렬 실행 변경은 [기획 대조 보고서](plan-alignment-report.md) 및 [README](../README.md)를 참고한다. 아래의 순차 실행·README 미변경·테스트 수는 각 작업 당시의 기록이다.

사용자가 수정한 `README.md`를 그대로 명세로 삼았다. README 26절에 따라 실제 Studio API 연결 전 단계까지만 구현한다.

## 파일과 역할

| 파일 | 상태 | 역할 |
|---|---|---|
| `app.py` | 교체 | Streamlit 업로드, 순차 실행, 저장, 5개 결과 탭, 예외 안내 |
| `config.py` | 교체 | `.env` 설정과 Mock 기본값, 입력 길이 상수 |
| `preprocessor.py` | 신규 | PyMuPDF 추출, 키워드와 앞뒤 페이지 선별, 페이지 마커, 글자 수 제한 |
| `agent_client.py` | 신규 | 후속 Studio 통신을 한곳에 모을 인터페이스; 현재 미연결 안내 |
| `business_agent.py` | 신규 | 고정된 가상 Business Fact JSON 및 스키마 검증 |
| `tech_agent.py` | 신규 | 고정된 가상 Tech/Investment Fact JSON 및 스키마 검증 |
| `insight_agent.py` | 신규 | 두 JSON만 받아 템플릿 기반 Mock 인사이트 생성 |
| `schemas.py` | 교체 | README의 3개 결과와 중첩 항목 검증 |
| `.env.example` | 교체 | 새 환경변수 예시, `USE_MOCK=true` |
| `requirements.txt` | 교체 | README의 5개 라이브러리, Python 3.11+ |
| `data/sample_report.pdf` | 신규 | 3페이지 한글 가상 보고서 |
| `tests/test_preprocessor.py` | 신규 | PDF·페이지 선별·길이·파일 오류 검증 |
| `tests/test_agents.py` | 교체 | 스키마·Mock·설정·Insight 입력 계약 검증 |
| `tests/test_workflow.py` | 교체 | PDF부터 JSON 저장까지 통합 및 저장 실패 검증 |
| `tests/test_presentation.py` | 교체 | Streamlit AppTest로 결과·파일 교체·오류·재시도 검증 |
| `agent_configs/README.md` | 교체 | 다음 단계용 프롬프트 및 연결 절차 |
| `docs/implementation-plan.md` | 교체 | 단계별 작업 및 검증 기록 |
| `.gitignore` | 수정 | 로컬 백업 제외, 샘플 PDF 추적 허용 |

이전 자동 수집·XML 처리·두 보고서 비교·CLI·Studio SDK 경로와 관련 테스트/데모는 제거했다. 현재 루트 Python 파일은 README가 요구한 8개다. 이전 `.env`는 변경하지 않았다.

수정 전 존재하던 소스·테스트·설정 예시·문서 36개는 `.migration-backup/before-readme-mvp-20260924.zip`에 보존했다. 삭제/교체 전에 원본 바이트 일치를 확인했다. 이 ZIP은 로컬 전용이며 Git에는 포함하지 않는다. Git에서 보이는 README 변경은 사용자가 먼저 수정한 내용이며 이번 작업으로 변경하지 않았다.

## 실행

프로젝트 루트의 PowerShell에서:

```powershell
# 가상환경이 없는 경우만 실행
py -3.11 -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# .env가 없는 경우만 복사한다. 기존 API 키 파일을 덮어쓰지 않는다.
if (!(Test-Path .env)) { Copy-Item .env.example .env }

# 기존 .env의 다른 설정과 무관하게 이번 세션에서 Mock을 선택
$env:USE_MOCK = "true"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

가상환경 활성화 후에는 README의 `streamlit run app.py`도 동일하다. 기존 `streamlit_app.py`와 `python app.py --mode demo` 명령은 더 이상 사용하지 않는다.

## 직접 테스트

1. 앱에서 파일 없이 `기업 분석하기`를 누르고 업로드 안내를 확인한다.
2. `data/sample_report.pdf`를 업로드하고 같은 버튼을 누른다.
3. 5개 탭과 Mock 경고를 확인한다. 근거 탭의 위쪽은 가상 Fact, 아래쪽은 업로드 PDF의 실제 원문이다.
4. `output/business_input.txt`, `tech_input.txt`의 `===== PAGE N =====`과 한글을 확인한다.
5. `output/business_result.json`, `tech_result.json`, `insight_result.json`을 확인한다.
6. 다른 PDF를 선택하면 이전 결과가 지워지는지 확인한다. 빈 파일/손상 PDF에서는 안내 후 새 PDF로 재시도한다.

자동 테스트:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

AppTest는 실제 파일 업로드 위젯 대신 메모리 업로드 객체를 공급하고, 나머지 Streamlit 실행·실제 PDF 전처리·Mock·저장을 실행한다. 외부 API는 호출하지 않는다.

## Mock 범위와 저장

- PDF 읽기, 한글 추출, 페이지 선별, 입력 TXT 생성, 스키마 검증, JSON 저장, 화면은 실제 코드다.
- Business/Tech는 업로드 내용과 무관한 고정 가상 JSON이다.
- Insight는 두 JSON의 Fact를 템플릿으로 조합한다. LLM 추론이 아니다. 입력 Fact가 없으면 관련 인사이트를 만들지 않는다.
- Mock의 source_page는 동봉된 가상 샘플의 페이지다. 다른 PDF에 대한 근거로 사용하지 않는다.
- 다섯 출력 파일은 최신 성공 실행으로 덮어쓴다. Agent 실패 시 저장하지 않으며, 파일 교체 중 일반적인 I/O 실패가 발생하면 앞서 교체한 파일을 복원한다.
- 출력 파일은 로컬에 남고 Git에는 포함되지 않는다. 업로드 원본의 임시 사본은 처리 후 삭제한다.

## 후속 Studio 연결

`agent_client.py`의 `run_agent`에 실제 요청/응답 처리를 구현해야 한다. Key와 세 Agent ID, endpoint가 필요하며 현재 계정의 정확한 API 사양/요청·응답 예시를 확인해야 한다. `USE_MOCK=false`만으로 실제 분석이 동작하지 않는다. 현재는 설정 누락 또는 Phase 3 미구현 안내를 반환한다.

자세한 프롬프트·스키마·연결점은 `agent_configs/README.md`에 기록했다. Key를 코드에 넣거나 기존 `.env`의 키를 출력하지 않았다.

## 한계와 검증 범위

- 초기 키워드 전처리에서는 `data/demo/[기아][정정]반기보고서(2026.09.16).pdf` 309페이지 중 Business 237페이지, Tech 94페이지를 선별했고 두 입력 모두 120,000자 제한과 경고가 적용됐다. 이는 초기 구현의 검증 기록이며 현재의 장/절 기반 선별 결과는 아래 추가 검증에 기록했다. 실제 Agent 분석 정확도는 아직 검증하지 않았다.
- 스캔 OCR은 구현하지 않았다. 텍스트 없는 PDF는 안내하며 일부 페이지만 비어 있어도 경고한다.
- 키워드가 없는 범주의 입력은 빈 문자열이다. Mock 결과는 예시이므로 이 경우에도 표시할 수 있다.
- 120,000자 제한 이후 내용은 제외되고 경고한다. 장문 보고서의 정보 누락 가능성은 후속 단계에서 평가해야 한다.
- PDF 파일의 1부터 시작하는 물리적 페이지 번호를 사용한다. 보고서에 인쇄된 쪽수와 다를 수 있다.
- 단일 사용자 로컬 MVP다. 다중 사용자 동시 저장, 프로세스 강제 종료/디스크 장애 시 트랜잭션 복구는 보장하지 않는다.
- 브라우저 자동화 연결이 없어 브라우저 직접 조작은 검증하지 못했다. Streamlit 서버 기동과 AppTest 화면 흐름으로 검증했다.

구현 참고: [PyMuPDF 텍스트 추출 공식 문서](https://pymupdf.readthedocs.io/en/latest/recipes-text.html), [Streamlit AppTest 공식 문서](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).

## 초기 MVP 검증 결과

- 자동 테스트 29개 통과: PDF 전처리 8개, Agent/설정 8개, UI 7개, 워크플로 6개.
- 한글 샘플 3페이지와 실제 보고서 309페이지의 Mock 파이프라인 성공.
- 샘플 PDF 3페이지를 PNG로 렌더링하여 한글·페이지 번호·잘림 여부 확인.
- 전체 Python 컴파일 성공, `git diff --check` 통과, 이전 구조를 import하는 코드 없음.
- Streamlit 서버 `http://127.0.0.1:8503` 기동 및 health HTTP 200 확인.
- 별도 코드 검토의 저장 중 파일 잠금 사례는 회귀 테스트 2개로 재현 후 복원 처리로 해결.
- README가 작업 전 백업과 바이트 단위로 동일한지 확인했다.

## Studio 업로드용 PDF 준비 (2026-09-25)

앱에 PDF를 업로드하고 `Studio용 PDF 만들기`를 누르면 Business·Tech PDF와 `manifest.json`을 내려받을 수 있다. Agent 호출 없이 실행하며, `기업 분석하기`의 Mock 결과와 별개다. 업로드 파일을 교체하거나 제거하면 화면의 이전 다운로드도 초기화된다.

CLI에서도 실행할 수 있다.

```powershell
.\.venv\Scripts\python.exe preprocessor.py "data/demo/[기아][정정]반기보고서(2026.09.16).pdf"
```

결과는 실행마다 새로운 `output/studio_inputs/report-<id>/`에 저장된다. `--output-dir`로 상위 저장 폴더를 지정할 수 있다.

- `business_input.pdf`: 회사 소개와 사업의 내용 장.
- `tech_input.pdf`: 회사 소개, 연구개발·설비 등 관련 절, 요약재무정보와 직원 현황.
- `manifest.json`: 원본 파일명·SHA-256, 선별 방법, 원본 페이지 목록, 파일 페이지와 원본 페이지 대응, 경고.

PDF 책갈피를 우선 사용하고, 없으면 페이지 상단 장/절 제목을 찾는다. 사업의 내용 구간을 식별하지 못하면 기존 키워드와 앞뒤 1페이지 방식으로 선별하고 경고한다. 재무제표 주석 안의 동명 ‘회사의 개요’는 공통 회사 소개에 포함하지 않는다.

선별 페이지의 표와 본문 배치를 유지하고, 상단에 별도 여백을 추가해 `SOURCE PDF PAGE N`을 표시한다. Agent의 `source_page`에는 이 N을 사용한다. PDF의 새 순서(`FILE PAGE`)나 하단 인쇄 쪽수와 구분한다. PDF 출력은 글자 수로 자르지 않으며 기존 TXT 입력의 120,000자 제한은 유지된다.

스캔 전용 PDF의 OCR과 모든 보고서 형식의 선별 정확도는 지원·보장하지 않는다. 선택된 이미지 페이지는 PDF에 보존되지만, 키워드나 제목을 읽을 수 없는 페이지는 선별에서 누락될 수 있다. PDF 주석·첨부파일·양식의 상호작용 보존은 검증 범위 밖이다. 실제 Studio 업로드와 API 호출은 아직 검증하지 않았다. `.env.example`의 DART 키와 CONFIG ID는 후속 연결용 예시이며 현재 코드에서 사용하지 않는다.

### 추가 검증

- 전체 자동 테스트 39개 통과: 기존 29개, Studio 전처리 7개, Studio UI 3개.
- 주석 속 ‘회사의 개요’ 오선별을 책갈피 유무 두 경우에서 재현한 뒤 상위 장 범위 확인으로 수정했다.
- 기아 보고서 309페이지에서 Business 46페이지, Tech 36페이지를 선별했다. 각각 추출 텍스트 62,786자와 55,843자이며 선별 경고는 없다.
- 현재 결과: `output/studio_inputs/report-70ad75cdafad/`. 이전 `report-1dfca7fc6036/`는 수정 전 결과이므로 새 결과를 사용한다.
- 원본 SHA-256과 모든 출력 페이지의 원본 번호를 확인했다. 82개 출력 페이지 본문의 렌더링 픽셀이 원본과 일치했으며 각 PDF의 첫·중간·마지막 페이지 PNG를 육안 검토했다.
- Python 컴파일과 `git diff --check` 통과. 실제 API 호출과 `.env` 수정은 수행하지 않았다.
