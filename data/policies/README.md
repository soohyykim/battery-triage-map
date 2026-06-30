# 정책 RAG 수집 문서 (data/policies/)

services/rag.py 가 이 폴더의 *.pdf 를 ChromaDB에 임베딩합니다.

| 파일명(권장) | 문서 | 출처 |
|---|---|---|
| used_battery_act.pdf | 사용후배터리법 | https://www.law.go.kr |
| waste_management_act.pdf | 폐기물관리법 | https://www.law.go.kr |
| me_transport_guideline.pdf | 환경부 배터리 운송·보관 가이드라인 | https://www.me.go.kr |
| motie_infra_plan_20240710.pdf | 산업부 사용후 배터리 법·제도·인프라 구축방안 | https://www.motie.go.kr |

적재: python -m services.rag
