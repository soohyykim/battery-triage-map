# Battery Triage Map

전기차 사용후 배터리의 위험도·화학계를 AI로 즉시 판정하고 지역 처리기업을 연결하는 의사결정 지원 플랫폼.

> 제14회 산업통상자원부 공공데이터 활용 아이디어 공모전 (마감 2026.07.06)

## 실행
```bash
pip install -r requirements.txt
cp .env.example .env
python data/init_db.py
uvicorn api.main:app --reload   # -> http://127.0.0.1:8000/docs
streamlit run app.py
```

## API 엔드포인트
| Method | Path | 설명 | 담당 |
|---|---|---|---|
| GET | / | 헬스체크 | - |
| POST | /triage | Rule Engine (위험도) | services/rule.py [팀장] |
| POST | /score | 등급·화학계 판정 | services/triage.py [데엔] |
| POST | /match | 처리기업 매칭 | services/matching.py [데엔] |
| POST | /report | 정책 RAG 리포트 | services/rag.py [백엔드/AI] |

## SQLite 스키마
- triage_history: 배터리 판정 이력
- companies: 처리업체 DB
- match_history: 매칭 이력

## 일정
- W1 (6/17~6/23): FastAPI 골격 · SQLite · ChromaDB 초기화 ✅
- W2 (6/24~6/27): 임베딩 완성 · /triage /score 구현
- W3 (6/28~7/4): /match /report · PDF 2종 · SC 배포
