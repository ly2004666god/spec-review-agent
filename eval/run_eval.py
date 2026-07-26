"""评测脚本：检验检索层能否召回期望条文/关键词。

只测检索（不测 LLM 生成），因为检索是 RAG 质量的瓶颈，且可自动判分：
- 关键词命中：期望关键词是否出现在召回内容里
- 条文命中：期望条文号是否出现在召回块的元数据里
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrieval.retriever import retrieve  # noqa: E402


def main():
    data = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    questions = data["questions"]
    kw_hits = clause_hits = 0

    for q in questions:
        docs = retrieve(q["query"])
        text = "\n".join(d.page_content for d in docs)
        clauses = {d.metadata.get("clause") for d in docs}

        kw_ok = all(kw in text for kw in q.get("expect_keywords", []))
        clause_ok = (not q.get("expect_clause")) or q["expect_clause"] in clauses
        kw_hits += kw_ok
        clause_hits += clause_ok
        mark = "✅" if (kw_ok and clause_ok) else "❌"
        print(f"{mark} Q{q['id']}: {q['query'][:30]}…  关键词={'中' if kw_ok else '未中'}  "
              f"条文={'中' if clause_ok else '未中'}")

    n = len(questions)
    print(f"\n关键词命中率 {kw_hits}/{n} = {kw_hits/n:.0%}   "
          f"条文命中率 {clause_hits}/{n} = {clause_hits/n:.0%}")


if __name__ == "__main__":
    main()
