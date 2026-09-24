# README MVP 전환 계획 및 검증 기록

> 아래는 초기 구현 및 Studio PDF 준비 작업의 이력이다. 2026-09-25 확정 기획 반영으로 README를 갱신하고 Extract 실행을 병렬화했다. 현재 기준은 [README](../README.md), 후속 변경·검증은 [기획 대조 보고서](plan-alignment-report.md)를 따른다. 아래의 순차 분석·README 미변경 표현은 당시 기록이다.

**Goal:** README의 Phase 1 + Phase 2를 로컬에서 끝까지 실행하고 중단한다.
**Spec:** `README.md` (사용자가 수정한 명세, 변경하지 않음).
**Architecture:** app → preprocessor → Business/Tech Mock → Insight Mock → 5개 탭.
**Tech Stack:** Python 3.11+, Streamlit, PyMuPDF, python-dotenv, pydantic; requests는 다음 단계용.

## 작업 원칙

- 현재 작업 폴더에서 순차 구현한다. 기존 미커밋 변경을 초기화하지 않는다.
- 수정 전 소스·테스트·설정 예시·문서 36개는 `.migration-backup/before-readme-mvp-20260924.zip`에 보존했다. `.env`는 백업·출력·수정하지 않는다.
- 기존 자동 수집, 비교, SDK, XML 데모 코드는 백업과 바이트 일치를 확인한 후 제거한다. 옛 테스트는 새 계약에 맞게 교체한다.
- 실제 Studio API 호출, 자동 수집, 비교, RAG, DB, 비동기는 범위 밖이다.
- Mock은 가상 예시이며 업로드 문서의 사실로 표시하지 않는다. 실제 PDF 텍스트와 Mock 근거를 분리한다.
- MAX_INPUT_CHARS=120000. 페이지 마커가 잘리지 않게 하고 누락을 안내한다.
- 숫자 누락은 `-`, JSON은 UTF-8, 비정상 Agent 타입은 스키마에서 거부한다.

## 순차 목표

### Goal 1 — 업로드 및 전처리

- [x] `app.py`: 제목·설명·PDF 업로드·버튼·5개 빈 탭. 미업로드 클릭은 안내.
- [x] `config.py`, `.env.example`, `requirements.txt`: 최소 설정과 의존성.
- [x] `preprocessor.py`: README의 4개 함수. 1부터 시작하는 PDF 페이지, 키워드·앞뒤 1페이지·중복 제거·120000자 제한.
- [x] `tests/test_preprocessor.py`: 실제 PDF 추출, 경계·중복·공백/대소문자, 잘못된/빈/암호화 PDF, 키워드 없음, 길이 제한 검증.
- 검증: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_preprocessor.py -v`와 초기 화면 AppTest.

### Goal 2 — Mock Agent 및 결과 화면

- [x] `schemas.py`: BusinessResult, TechResult, InsightResult 및 중첩 항목.
- [x] `business_agent.py`, `tech_agent.py`, `insight_agent.py`: 독립 Mock JSON 반환 및 검증. Insight 입력은 두 JSON만.
- [x] `agent_client.py`: 미래 API 통신 경계. 현재는 설정 누락 또는 Phase 3 미구현을 안내하며 네트워크 호출 없음.
- [x] `app.py`: 순차 분석, 2개 txt·3개 JSON 저장, 5개 탭, 실제 원문 조회, 오류·재업로드 상태 초기화.
- [x] `tests/test_agents.py`, `tests/test_workflow.py`, `tests/test_presentation.py`: 입력 계약, 네트워크 미호출, 잘못된 결과·저장 실패·재시도·상태 초기화, UI 출력.
- 검증: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.

### Goal 3 — 통합 검증 및 보고

- [x] `data/sample_report.pdf`: 가상 기업 한글 샘플. PDF → 전처리 → Mock 3개 → 저장 및 Streamlit 화면 검증.
- [x] 새 구조의 Agent 프롬프트와 사용 안내 작성.
- [x] 전체 테스트, compileall, 이전 구조 import 잔존, 실행 서버 확인.
- [x] 파일 역할·명령·테스트·Mock 범위·Studio 후속 연결점·제한사항 보고.

## 중점 검증

1. 스캔/암호화/손상 PDF: 이해 가능한 안내, traceback 미노출.
2. 키워드 없는 문서·부분 스캔: 전체 문서를 임의 전달하지 않고 누락 안내.
3. 대용량 입력: 마커와 최대 길이를 보존하고 잘림 안내.
4. Mock 사실/페이지를 업로드 원문으로 오인하지 않게 표시.
5. 두 번째 업로드 또는 실패 이후 이전 결과가 남지 않음.

## 실행 기록

- 기존 36개 파일 ZIP 백업 무결성 확인. 가상환경에 PyMuPDF 1.28.2 설치.

- Goal 1 완료: 초기 화면 및 전처리 9개 테스트 통과 후 Goal 2 진행.
- Goal 2 완료: Mock Agent·설정·통합·화면 테스트를 순차 추가하여 27개 통과.
- 최종 검토: 저장 중 파일 잠금으로 이전/현재 결과가 섞이는 사례를 재현했다. 두 회귀 테스트 실패를 확인하고 이전 파일 복원 처리를 추가하여 전체 29개 통과.
- Goal 3 완료: 한글 샘플 3페이지와 기아 정정 반기보고서 309페이지의 Mock 종단간 실행 성공. 실제 보고서의 두 입력은 각각 120000자로 제한되었으며 화면 잘림 경고와 마지막 페이지 조회 검증.
- compileall, git diff --check, 이전 구조 import 잔존 검사 통과. 서버 health HTTP 200.
- README는 백업과 바이트 일치, .env는 수정하지 않음. API는 호출하지 않음.
- 범위 판단: 실제 Studio 통신·추출 정확도·투자판단은 후속 Phase 3 대상. 다중 사용자 동시 저장·악성 PDF 자원 고갈 방어는 교육용 단일 사용자 MVP 범위 밖이며 운영용으로 사용하려면 별도 작업이 필요하다.
- 사용 안내 및 전체 파일 역할: docs/mvp-report.md. 브라우저 연결이 없어 브라우저 직접 조작 대신 AppTest로 검증했다.

## Studio PDF 준비 후속 작업 (2026-09-25)

- [x] 진행 중이던 장/절 기반 전처리와 Studio PDF 생성 UI/CLI 변경분 검토.
- [x] 기존 38개 테스트 통과 확인.
- [x] 실제 보고서 검토에서 주석 속 동명 회사 개요 오선별 발견. 책갈피/텍스트 제목 두 경로의 실패 재현 후 상위 장 범위 확인으로 수정.
- [x] 회귀 테스트 포함 전체 39개 통과.
- [x] 수정된 로직으로 기아 보고서 재출력: Business 46페이지, Tech 36페이지. `output/studio_inputs/report-70ad75cdafad/`에 저장.
- [x] 사용 안내와 Agent source_page 지침 갱신. 실제 Studio 통신은 후속 Phase 3 범위로 유지.
- [x] 출력 82페이지 본문 픽셀과 원본 일치, 대표 6페이지 PNG 검토, 컴파일 및 diff 공백 검사 통과.
