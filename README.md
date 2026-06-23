# Battery Triage Map

?꾧린李??ъ슜??諛고꽣由ъ쓽 ?꾪뿕?꽷룻솕?숆퀎瑜?AI濡?利됱떆 ?먯젙?섍퀬 吏??泥섎━湲곗뾽???곌껐?섎뒗 ?섏궗寃곗젙 吏???뚮옯??

> ??4???곗뾽?듭긽?먯썝遺 怨듦났?곗씠???쒖슜 ?꾩씠?붿뼱 怨듬え??(留덇컧 2026.07.06)

## ?ㅽ뻾
```bash
pip install -r requirements.txt
cp .env.example .env
python data/init_db.py
uvicorn api.main:app --reload   # -> http://127.0.0.1:8000/docs
streamlit run app.py
```

## API ?붾뱶?ъ씤??| Method | Path | ?ㅻ챸 | ?대떦 |
|---|---|---|---|
| GET | / | ?ъ뒪泥댄겕 | - |
| POST | /triage | Rule Engine (?꾪뿕?? | services/rule.py [??? |
| POST | /score | ?깃툒쨌?뷀븰怨??먯젙 | services/triage.py [?곗뿏] |
| POST | /match | 泥섎━湲곗뾽 留ㅼ묶 | services/matching.py [?곗뿏] |
| POST | /report | ?뺤콉 RAG 由ы룷??| services/rag.py [諛깆뿏??AI] |

## SQLite ?ㅽ궎留?- triage_history: 諛고꽣由??먯젙 ?대젰
- companies: 泥섎━?낆껜 DB
- match_history: 留ㅼ묶 ?대젰

## ?쇱젙
- W1 (6/17~6/23): FastAPI 怨④꺽 쨌 SQLite 쨌 ChromaDB 珥덇린????- W2 (6/24~6/27): ?꾨쿋???꾩꽦 쨌 /triage /score 援ы쁽
- W3 (6/28~7/4): /match /report 쨌 PDF 2醫?쨌 SC 諛고룷
