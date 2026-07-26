"""用 config 里当前的 EMBEDDING_MODEL 重建所有规范的向量索引。

切好的文档块就存在 FAISS 的 docstore 里，直接取出来重新向量化，
不需要重新解析 PDF / 重跑 OCR。换 embedding 模型后运行本脚本即可。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_community.vectorstores import FAISS  # noqa: E402

from store import manager  # noqa: E402


def main():
    reg = manager.list_specs()
    if not reg:
        print("registry 为空，没有可重建的规范。")
        return
    # 用旧索引里存的文档块，配新 embedding 重建
    BATCH = 64  # 一次全量提交会把 Ollama 撑崩，分批喂
    for sid, info in reg.items():
        t0 = time.time()
        old = manager.load_stores([sid])[sid]
        docs = list(old.docstore._dict.values())
        new_vs = None
        for i in range(0, len(docs), BATCH):
            batch = docs[i:i + BATCH]
            if new_vs is None:
                new_vs = FAISS.from_documents(batch, manager.embeddings)
            else:
                new_vs.add_documents(batch)
            print(f"  {sid}: {min(i+BATCH, len(docs))}/{len(docs)}", flush=True)
        new_vs.save_local(str(manager.STORE_DIR / sid))
        print(f"✅ {sid}: {len(docs)} 块重建完成，耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
