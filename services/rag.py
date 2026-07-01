"""
services/rag.py
정책 RAG 파이프라인 (백엔드/AI 담당).

파이프라인:
  data/policies/*.pdf
   -> PyMuPDF 텍스트 추출
   -> 조문 단위(제N조) 청크 분할
   -> ChromaDB 임베딩 저장 (무료 로컬 임베딩, API 키 불필요)
   -> grade·처리방향 기반 조문 검색
   -> 리포트 생성 (LLM 키 있으면 문장 합성, 없으면 근거 발췌형)

임베딩: ChromaDB 기본 임베딩(onnxruntime, 로컬·무료). OPENAI 키 불필요.
리포트 생성: OPENAI_API_KEY 가 있으면 LLM 으로 다듬고, 없으면 템플릿+발췌로 동작.

수집 문서(data/policies/): 반납고시 · 분리보관규정 · 자원순환시행령 · 산업육성법 · 순환이용방안
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent
POLICY_DIR = Path(os.getenv("POLICY_DIR", BASE_DIR / "data" / "policies"))
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", BASE_DIR / "data" / "chroma"))
COLLECTION_NAME = "btm_policy"
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Gemini (무료) — 서버 메모리 절약용 원격 임베딩 + 리포트 생성
#   GEMINI_API_KEY 가 있으면: 임베딩/생성을 Gemini로 (로컬 모델 미사용 → 메모리 가벼움, 배포용)
#   없으면: ChromaDB 기본 로컬 임베딩 (로컬 개발용)
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "models/gemini-embedding-001")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# 조문 단위 청크가 너무 길면 잘라줄 상한
MAX_CHARS = 1200


def _gemini_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _embed_texts(texts: List[str]) -> List[List[float]] | None:
    """
    Gemini 로 텍스트들을 임베딩한다. 키가 없으면 None 을 반환해
    호출부가 ChromaDB 기본(로컬) 임베딩으로 동작하게 한다.
    """
    key = _gemini_key()
    if not key:
        return None
    import time
    import google.generativeai as genai

    genai.configure(api_key=key)
    vectors: List[List[float]] = []
    for i in range(0, len(texts), 20):            # 20개씩 배치
        batch = texts[i:i + 20]
        for attempt in range(6):                  # 429 면 대기 후 재시도
            try:
                resp = genai.embed_content(model=GEMINI_EMBED_MODEL, content=batch)
                emb = resp["embedding"]
                if emb and not isinstance(emb[0], list):  # 단일 입력 방어
                    emb = [emb]
                vectors.extend(emb)
                break
            except Exception as e:
                if "429" in str(e) and attempt < 5:
                    print("[rag] 임베딩 rate limit -> 25초 대기 후 재시도")
                    time.sleep(25)
                    continue
                raise
        time.sleep(1)                             # 배치 간 간격(분당 한도 여유)
    return vectors

DISCLAIMER = (
    "본 결과는 입력값 기반 예비 추정이며, 법적 지위(순환자원/폐기물)와 "
    "최종 처리경로는 처리업체 실측 이후 확정됩니다. "
    "Battery Triage Map은 판정·매칭 플랫폼으로, 직접 수거를 수행하지 않습니다."
)


# ---------------------------------------------------------------------------
# 1. PDF 텍스트 추출 (PyMuPDF)
# ---------------------------------------------------------------------------
def extract_text(pdf_path: str | Path) -> str:
    """단일 PDF -> 전체 텍스트. PyMuPDF(fitz) 사용."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def load_policy_texts() -> List[dict]:
    """data/policies/*.pdf 전체를 추출하여 [{source, text}, ...] 반환."""
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    docs: List[dict] = []
    for pdf in sorted(POLICY_DIR.glob("*.pdf")):
        docs.append({"source": pdf.name, "text": extract_text(pdf)})
        print(f"[rag] 추출 완료: {pdf.name} ({len(docs[-1]['text'])} chars)")
    if not docs:
        print(f"[rag] {POLICY_DIR} 에 PDF 없음. data/policies/README.md 참고.")
    return docs


# ---------------------------------------------------------------------------
# 2. 조문 단위 청크 분할
# ---------------------------------------------------------------------------
_ARTICLE_RE = re.compile(r"(제\s*\d+\s*조(?:의\s*\d+)?)")


def split_by_article(text: str) -> List[dict]:
    """
    법령 텍스트를 '제N조' 경계로 분할한다.
    조문 마커가 없으면(보도자료 등) 길이 기준으로 자른다.
    반환: [{article, content}, ...]
    """
    text = re.sub(r"[ \t]+\n", "\n", text)
    parts = _ARTICLE_RE.split(text)

    chunks: List[dict] = []
    if len(parts) <= 1:
        # 조문 구조 없음 -> 길이 기준 분할
        for i in range(0, len(text), MAX_CHARS):
            body = text[i:i + MAX_CHARS].strip()
            if body:
                chunks.append({"article": "", "content": body})
        return chunks

    # parts = [머리말, 제1조, 본문, 제2조, 본문, ...]
    head = parts[0].strip()
    if head:
        chunks.append({"article": "머리말", "content": head[:MAX_CHARS]})

    for i in range(1, len(parts), 2):
        marker = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        content = f"{marker} {body}".strip()
        # 너무 긴 조문은 추가로 자름
        for j in range(0, len(content), MAX_CHARS):
            piece = content[j:j + MAX_CHARS].strip()
            if piece:
                chunks.append({"article": marker, "content": piece})
    return chunks


# ---------------------------------------------------------------------------
# 3. ChromaDB (무료 로컬 임베딩)
# ---------------------------------------------------------------------------
def get_chroma_client():
    """영속(PersistentClient) ChromaDB 클라이언트 반환."""
    import chromadb
    from chromadb.config import Settings

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    # 텔레메트리 끔(로그 노이즈 + 약간의 메모리 절약)
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def get_collection():
    """
    정책 문서 컬렉션 핸들 확보(없으면 생성).
    임베딩 함수를 지정하지 않으면 ChromaDB 기본(로컬, 무료) 임베딩을 쓴다.
    """
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# 4. 임베딩 인덱스 구축
# ---------------------------------------------------------------------------
def _merge_chunks(chunks: List[dict], max_chars: int = 2000) -> List[dict]:
    """
    잘게 쪼개진 조문 청크들을 max_chars 까지 합쳐 청크 수를 줄인다.
    (무료 임베딩 분당 한도(100건)와 호출 비용을 줄이려는 목적. 검색 품질엔 큰 지장 없음)
    """
    merged: List[dict] = []
    buf_text, buf_article = "", ""
    for c in chunks:
        piece = c["content"]
        if buf_text and len(buf_text) + len(piece) > max_chars:
            merged.append({"article": buf_article, "content": buf_text.strip()})
            buf_text, buf_article = "", ""
        if not buf_article and c.get("article"):
            buf_article = c["article"]
        buf_text += ("\n" + piece) if buf_text else piece
    if buf_text.strip():
        merged.append({"article": buf_article, "content": buf_text.strip()})
    return merged


def build_index(reset: bool = True) -> int:
    """정책 PDF -> 조문 청크 -> ChromaDB 적재. 적재 청크 수 반환."""
    client = get_chroma_client()
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    total = 0
    for doc in load_policy_texts():
        source = doc["source"]
        chunks = _merge_chunks(split_by_article(doc["text"]))
        if not chunks:
            continue
        ids = [f"{source}::{i}" for i in range(len(chunks))]
        documents = [c["content"] for c in chunks]
        metadatas = [{"source": source, "article": c["article"]} for c in chunks]
        # 키 있으면 Gemini 임베딩을 직접 넣고(로컬 모델 미로딩), 없으면 기본 로컬 임베딩
        embeddings = _embed_texts(documents)
        if embeddings is not None:
            collection.add(ids=ids, documents=documents,
                           metadatas=metadatas, embeddings=embeddings)
        else:
            collection.add(ids=ids, documents=documents, metadatas=metadatas)
        total += len(chunks)
        print(f"[rag] {source} -> {len(chunks)} chunks 적재")
    print(f"[rag] 완료. 총 {total} chunks (collection={COLLECTION_NAME})")
    return total


# ---------------------------------------------------------------------------
# 5. 검색
# ---------------------------------------------------------------------------
def search_policies(query: str, n_results: int = 4) -> List[dict]:
    """질의와 관련된 조문 상위 n개를 반환. [{source, article, content}, ...]"""
    collection = get_collection()
    if collection.count() == 0:
        # 배포 환경 안전망: 인덱스가 비어있으면 1회 자동 구축한다.
        # (정책 PDF가 repo에 포함돼 있어야 가능. 실패해도 빈 결과로 안전하게 처리.)
        try:
            print("[rag] 인덱스 비어있음 -> 자동 구축 시도")
            build_index(reset=False)
            collection = get_collection()
        except Exception as e:
            print(f"[rag] 자동 인덱싱 실패(빈 결과 반환): {e}")
            return []
        if collection.count() == 0:
            return []
    # 키 있으면 질의도 Gemini로 임베딩(인덱스와 동일 방식), 없으면 기본 로컬 임베딩
    qvec = _embed_texts([query])
    if qvec is not None:
        res = collection.query(query_embeddings=qvec, n_results=n_results)
    else:
        res = collection.query(query_texts=[query], n_results=n_results)
    out: List[dict] = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    for content, meta in zip(docs, metas):
        out.append({
            "source": meta.get("source", ""),
            "article": meta.get("article", ""),
            "content": content,
        })
    return out


# ---------------------------------------------------------------------------
# 6. 리포트 생성 — /report 엔드포인트가 호출
# ---------------------------------------------------------------------------
_PATH_KO = {
    "reuse_candidate": "재사용 후보",
    "reuse_or_recycle_after_diagnosis": "진단 후 재사용/재활용",
    "recycle_candidate": "재활용 후보",
    "diagnosis_required": "정밀 진단 필요",
    "designated_waste": "지정폐기물 처리",
}


def _build_query(triage_result: dict, question: str | None) -> str:
    """등급·처리방향·화학계로 검색 질의를 만든다."""
    if question:
        return question
    grade = triage_result.get("grade", "")
    path = triage_result.get("recommended_path", "")
    chem = triage_result.get("input_summary", {}).get("chemistry", "")
    return f"{chem} 배터리 {_PATH_KO.get(path, path)} 처리 절차 분리 보관 반납 기준 {grade}"


def _compose_with_gemini(triage_result: dict, contexts: List[dict], question: str | None) -> str | None:
    """GEMINI_API_KEY 가 있으면 Gemini 로 리포트를 합성한다. 없으면 None."""
    key = _gemini_key()
    if not key:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=key)
        ctx = "\n\n".join(
            f"[{c['source']} {c['article']}]\n{c['content']}" for c in contexts
        )
        grade = triage_result.get("grade", "")
        path = _PATH_KO.get(triage_result.get("recommended_path", ""), "")
        prompt = (
            "너는 전기차 사용후 배터리 처리 정책 안내 도우미다. "
            "아래 정책 조문만 근거로, '판정 근거 / 관련 법령 / 주의사항' 형식으로 "
            "간결한 한국어로 답하라. 조문에 없는 내용은 지어내지 마라.\n\n"
            f"[배터리 예비판정] 등급={grade}, 처리방향={path}\n"
            f"[질문] {question or '이 배터리의 처리 절차와 법적 근거를 알려줘'}\n\n"
            f"[정책 조문]\n{ctx}"
        )
        model = genai.GenerativeModel(GEMINI_MODEL)
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        return text or None
    except Exception as e:
        print(f"[rag] Gemini 생성 실패, 다음 단계로 대체: {e}")
        return None


def _compose_with_llm(triage_result: dict, contexts: List[dict], question: str | None) -> str | None:
    """OPENAI_API_KEY 가 있으면 LLM 으로 리포트를 합성한다. 없으면 None."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-xxxx"):
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    ctx = "\n\n".join(
        f"[{c['source']} {c['article']}]\n{c['content']}" for c in contexts
    )
    grade = triage_result.get("grade", "")
    path = _PATH_KO.get(triage_result.get("recommended_path", ""), "")
    user = (
        f"배터리 예비 판정: 등급={grade}, 처리방향={path}.\n"
        f"질문: {question or '이 배터리의 처리 절차와 법적 근거를 알려줘'}\n\n"
        f"아래 정책 조문만 근거로 사용해 한국어로 답하라.\n{ctx}"
    )
    sys = (
        "너는 전기차 사용후 배터리 처리 정책 안내 도우미다. "
        "주어진 조문만 근거로, 2~3문장 판정 근거 + 관련 법령 + 주의사항 형식으로 간결히 답하라. "
        "조문에 없는 내용은 지어내지 마라."
    )
    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[rag] LLM 호출 실패, 템플릿으로 대체: {e}")
        return None


def _compose_template(triage_result: dict, contexts: List[dict]) -> str:
    """LLM 없이 검색된 조문을 근거로 발췌형 리포트를 만든다."""
    grade = triage_result.get("grade", "")
    path = _PATH_KO.get(triage_result.get("recommended_path", ""), "")
    chem = triage_result.get("input_summary", {}).get("chemistry", "")
    route = triage_result.get("collection_route", "")

    lines = [
        f"[판정 근거] 입력값 기반 예비 평가 결과 등급은 '{grade}', "
        f"예비 처리방향은 '{path}'로 추정됩니다. (화학계: {chem}, 수거 루트: {route})",
        "",
        "[관련 법령 근거]",
    ]
    if contexts:
        for c in contexts:
            snippet = c["content"][:220].replace("\n", " ").strip()
            tag = f"{c['source']} {c['article']}".strip()
            lines.append(f"· {tag}\n   {snippet}…")
    else:
        lines.append("· (정책 인덱스가 비어있음 — build_index() 실행 필요)")
    lines += ["", f"[주의사항] {DISCLAIMER}"]
    return "\n".join(lines)


def generate_report(payload: dict) -> dict:
    """
    배터리 판정 결과 기반 정책 RAG 리포트 생성.
    payload: {triage_result: {...}, matched_companies?: [...], question?: str}
    return : {report: str, sources: List[str]}
    """
    triage_result = payload.get("triage_result") or {}
    question = payload.get("question")

    query = _build_query(triage_result, question)
    contexts = search_policies(query, n_results=4)

    # 우선순위: Gemini(무료) -> OpenAI -> 템플릿(키 없이 발췌형)
    report = _compose_with_gemini(triage_result, contexts, question)
    if report is None:
        report = _compose_with_llm(triage_result, contexts, question)
    if report is None:
        report = _compose_template(triage_result, contexts)

    sources = sorted({f"{c['source']} {c['article']}".strip() for c in contexts})
    return {"report": report, "sources": sources}


if __name__ == "__main__":
    # 스모크: 인덱스 구축 후 샘플 리포트 출력
    n = build_index()
    sample = {
        "triage_result": {
            "grade": "Orange",
            "recommended_path": "recycle_candidate",
            "collection_route": "NCM 전용 수거 루트",
            "input_summary": {"chemistry": "NCM"},
        }
    }
    out = generate_report(sample)
    print("\n===== 샘플 리포트 =====")
    print(out["report"])
    print("\n출처:", out["sources"])
