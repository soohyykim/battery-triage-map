"""
services/rag.py - 정책 RAG 파이프라인 (백엔드/AI 담당)
W1: ChromaDB 초기 설정 + PyMuPDF 텍스트 추출 골격
W2: 임베딩 적재(build_index) + RetrievalQA(generate_report) 완성
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent
POLICY_DIR = Path(os.getenv("POLICY_DIR", str(BASE_DIR / "data" / "policies")))
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(BASE_DIR / "data" / "chroma")))
COLLECTION_NAME = "battery_policies"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

def extract_text(pdf_path) -> str:
    import fitz
    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()

def load_policy_texts() -> List[dict]:
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    docs = []
    for pdf in sorted(POLICY_DIR.glob("*.pdf")):
        docs.append({"source": pdf.name, "text": extract_text(pdf)})
        print(f"[rag] 추출 완료: {pdf.name}")
    if not docs:
        print(f"[rag] {POLICY_DIR} 에 PDF 없음. data/policies/README.md 참고.")
    return docs

def get_chroma_client():
    import chromadb
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))

def get_collection():
    return get_chroma_client().get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

def build_index() -> int:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    total = 0
    for doc in load_policy_texts():
        chunks = splitter.split_text(doc["text"])
        # TODO(W2): collection.add(ids=..., documents=chunks, metadatas=...)
        total += len(chunks)
        print(f"[rag] {doc['source']} -> {len(chunks)} chunks (적재 보류: W2)")
    return total

def generate_report(payload: dict) -> dict:
    # TODO(W2): RetrievalQA 체인 구성 후 구현
    raise NotImplementedError("RAG 리포트 생성은 W2에서 구현")

if __name__ == "__main__":
    col = get_collection()
    print(f"[rag] ChromaDB 준비 완료: {col.name} (count={col.count()})")
    build_index()
