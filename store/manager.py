"""多规范向量库管理：每份规范一个独立 FAISS 库 + registry.json 登记。

registry.json 结构：
{
  "gb50010": {"spec_name": "混凝土结构设计规范", "spec_code": "GB 50010-2010",
               "file": "原文件名.pdf", "chunks": 1234, "ocr_pages": 0}
}
"""
import json
import re
import shutil
import uuid

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from config import EMBEDDING_MODEL, OLLAMA_BASE_URL, REGISTRY_PATH, STORE_DIR

embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {}


def _save_registry(reg: dict):
    REGISTRY_PATH.write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _make_spec_id(spec_code: str) -> str:
    """用规范编号生成目录名，如 "GB 50010-2010" -> "gb-50010-2010"。"""
    slug = re.sub(r"[^a-z0-9]+", "-", spec_code.lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


def add_spec(docs: list[Document], spec_name: str, spec_code: str,
             source_file: str, ocr_pages: int = 0) -> str:
    """建库并登记。若同编号规范已存在则覆盖（视为更新版本）。"""
    spec_id = _make_spec_id(spec_code)
    store_path = STORE_DIR / spec_id
    if store_path.exists():
        shutil.rmtree(store_path)

    # 分批喂给 Ollama：一次提交几百块会把 embedding 服务撑崩
    BATCH = 64
    vs = None
    for i in range(0, len(docs), BATCH):
        batch = docs[i:i + BATCH]
        if vs is None:
            vs = FAISS.from_documents(batch, embeddings)
        else:
            vs.add_documents(batch)
    vs.save_local(str(store_path))

    reg = _load_registry()
    reg[spec_id] = {
        "spec_name": spec_name, "spec_code": spec_code,
        "file": source_file, "chunks": len(docs), "ocr_pages": ocr_pages,
    }
    _save_registry(reg)
    return spec_id


def list_specs() -> dict:
    return _load_registry()


def delete_spec(spec_id: str) -> bool:
    reg = _load_registry()
    if spec_id not in reg:
        return False
    shutil.rmtree(STORE_DIR / spec_id, ignore_errors=True)
    del reg[spec_id]
    _save_registry(reg)
    return True


def load_stores(spec_ids: list[str] | None = None) -> dict[str, FAISS]:
    """加载指定（或全部）规范的向量库。"""
    reg = _load_registry()
    ids = spec_ids if spec_ids else list(reg.keys())
    stores = {}
    for sid in ids:
        path = STORE_DIR / sid
        if sid in reg and path.exists():
            stores[sid] = FAISS.load_local(
                str(path), embeddings, allow_dangerous_deserialization=True
            )
    return stores
