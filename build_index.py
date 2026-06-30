from services import rag
if __name__ == "__main__":
    try:
        n = rag.build_index()
        print(f"[build_index] done: {n} chunks")
    except Exception as e:
        print(f"[build_index] failed (runtime fallback): {e}")
