"""混合检索：条文号精确匹配优先，语义向量检索兜底。

查询里出现 "6.3.1" 这类条文号时，向量检索对数字不敏感、召回很不可靠，
所以先按元数据精确查找该条文的所有块；再用向量检索补充语义相关内容。
"""
import re

from langchain_core.documents import Document

from config import RETRIEVE_K
from ingest.splitter import format_source
from store.manager import load_stores

CLAUSE_IN_QUERY_RE = re.compile(r"\b(\d{1,2}(?:\.\d{1,3}){1,3})\b")


def _exact_clause_lookup(stores, clause: str) -> list[Document]:
    """遍历库内所有块，按条文号元数据精确匹配（FAISS 无元数据索引，只能线扫）。"""
    hits = []
    for vs in stores.values():
        for doc in vs.docstore._dict.values():
            if doc.metadata.get("clause") == clause:
                hits.append(doc)
    return hits


def retrieve(query: str, spec_ids: list[str] | None = None) -> list[Document]:
    stores = load_stores(spec_ids)
    if not stores:
        return []

    results: list[Document] = []
    seen: set[str] = set()

    def add(doc: Document):
        key = doc.page_content[:100]
        if key not in seen:
            seen.add(key)
            results.append(doc)

    # 1. 条文号精确匹配
    for clause in CLAUSE_IN_QUERY_RE.findall(query):
        for doc in _exact_clause_lookup(stores, clause):
            add(doc)

    # 2. 向量检索（多库时每库都查，按相似度合并取前 K）
    scored = []
    for vs in stores.values():
        scored.extend(vs.similarity_search_with_score(query, k=RETRIEVE_K))
    scored.sort(key=lambda x: x[1])  # FAISS 距离越小越相似
    for doc, _score in scored[:RETRIEVE_K]:
        add(doc)

    return results


def build_context(docs: list[Document]) -> str:
    """把检索结果拼成带出处编号的上下文，供 LLM 引用。"""
    blocks = []
    for i, doc in enumerate(docs, 1):
        blocks.append(f"[{i}] {format_source(doc)}\n{doc.page_content}")
    return "\n\n".join(blocks)
