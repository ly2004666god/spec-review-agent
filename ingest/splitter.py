"""条文切分器：按规范条文号（如 6.3.1）切分，附完整元数据。

策略：
1. 逐行扫描，识别章标题（"6 承载能力…"）和条文号行（"6.3.1 …"）
2. 每个条文号之间的内容为一块 → 保证条文完整
3. 超长条文用递归切分兜底，但保留同一条文号元数据
4. 表格单独成块，标注所在页码
"""
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_MAX_CHARS, CHUNK_OVERLAP

# 条文号：行首 2~4 级数字编号，如 "6.3.1" / "6.3.1.2"。
# 允许编号后面无内容（有的 PDF 条文号单独占一行，正文在下一行）
CLAUSE_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,3}){1,3})[　 ]*(?=\S|$)")
# 章标题："6 承载能力极限状态计算" —— 行首单个数字 + 空格 + 中文
# 标题不含句读标点，否则会把条文内的子项（"1 伸入梁支座…不应少于两根。"）误判为章
CHAPTER_RE = re.compile(r"^\s*(\d{1,2})[　 ]+([一-鿿][^\n。；，：,;]{1,30})\s*$")

# --- 真实 PDF 的脏数据清洗 ---
# 行首编号的常见误识别：0→O/o/()、1→l/I、点后带空格
# 实例："3. O. 2"→3.0.2  "2. o. l()"→2.0.10
DIRTY_NUM_RE = re.compile(
    r"^\s*([0-9OolI()]{1,4}(?:\s*[.．]\s*[0-9OolI()]{1,4}){1,3})(?=[\s　]|[一-鿿]|$)")
# 目录行："2 术语…·……….. 2"（一串点/省略号 + 页码结尾）
TOC_LINE_RE = re.compile(r"[·…‥.]{4,}\s*\d*\s*$")
# 单独成行的章号（章标题被排版拆成两行："3" / "基本规定"）
LONE_NUM_RE = re.compile(r"^\s*(\d{1,2})\s*$")
# 纯中文短标题行（用于和上一行的章号拼接）
TITLE_LINE_RE = re.compile(r"^\s*([一-鿿][^\n。；，：,;、]{0,30})\s*$")


def _normalize_line(line: str) -> str:
    """修复行首编号的常见提取错误：O→0、点后空格、全角点。"""
    m = DIRTY_NUM_RE.match(line)
    if not m:
        return line
    num = re.sub(r"\s+", "", m.group(1)).replace("．", ".")
    num = num.replace("()", "0").replace("O", "0").replace("o", "0")
    num = num.replace("l", "1").replace("I", "1").replace("(", "").replace(")", "")
    # 清洗完必须是合法编号，否则保持原样（避免把正文行改坏）
    if not re.fullmatch(r"\d{1,2}(\.\d{1,3}){1,3}", num):
        return line
    return num + " " + line[m.end():].lstrip()

_fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_MAX_CHARS, chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", "；", " ", ""],
)


def split_pages(pages: list[dict], spec_name: str, spec_code: str) -> list[Document]:
    """输入 loader 的分页结果，输出带元数据的 Document 列表。"""
    docs: list[Document] = []
    current_chapter = ""
    current_clause = ""
    buffer: list[str] = []   # 当前条文累积的行
    buffer_page = 1          # 当前条文起始页

    def flush():
        """把缓冲区的条文写成 Document（超长则兜底切分）。"""
        nonlocal buffer
        content = "\n".join(buffer).strip()
        buffer = []
        if not content:
            return
        meta = {
            "spec_name": spec_name,
            "spec_code": spec_code,
            "clause": current_clause,
            "chapter": current_chapter,
            "page": buffer_page,
            "type": "clause" if current_clause else "text",
        }
        if len(content) <= CHUNK_MAX_CHARS:
            docs.append(Document(page_content=content, metadata=meta))
        else:
            for piece in _fallback_splitter.split_text(content):
                docs.append(Document(page_content=piece, metadata=dict(meta)))

    pending_chapter_num = ""  # 章号单独成行时暂存，等下一行标题

    for page in pages:
        page_no = page["page"]
        for raw_line in page["text"].splitlines():
            if not raw_line.strip():
                continue
            if TOC_LINE_RE.search(raw_line):
                continue  # 目录行：会带出假条文号，直接丢弃
            line = _normalize_line(raw_line)

            # 章标题拆成两行的情况："3" 单独一行 + "基本规定" 一行
            m_lone = LONE_NUM_RE.match(line)
            if m_lone:
                pending_chapter_num = m_lone.group(1)
                continue
            if pending_chapter_num:
                m_title = TITLE_LINE_RE.match(line)
                if m_title:
                    flush()
                    current_chapter = f"{pending_chapter_num} {m_title.group(1)}"
                    current_clause = ""
                    buffer_page = page_no
                    pending_chapter_num = ""
                    continue
                pending_chapter_num = ""  # 下一行不是标题，当普通数字忽略

            m_clause = CLAUSE_RE.match(line)
            m_chapter = CHAPTER_RE.match(line)
            if m_clause:
                flush()  # 上一条文结束
                current_clause = m_clause.group(1)
                buffer_page = page_no
                buffer.append(line.strip())
            elif m_chapter:
                flush()
                current_chapter = f"{m_chapter.group(1)} {m_chapter.group(2)}"
                current_clause = ""  # 新章开始，清空条文号
                buffer_page = page_no
            else:
                if not buffer:
                    buffer_page = page_no
                buffer.append(line.strip())
        # 页内表格单独成块（表格属于当前条文上下文）
        for md_table in page["tables"]:
            docs.append(Document(
                page_content=md_table,
                metadata={
                    "spec_name": spec_name, "spec_code": spec_code,
                    "clause": current_clause, "chapter": current_chapter,
                    "page": page_no, "type": "table",
                },
            ))
    flush()  # 最后一条
    return docs


def format_source(doc: Document) -> str:
    """把一个块的出处格式化成引用字符串，用于回答中标注。"""
    m = doc.metadata
    parts = [f"《{m.get('spec_name', '?')}》"]
    if m.get("spec_code"):
        parts.append(m["spec_code"])
    if m.get("clause"):
        parts.append(f"第 {m['clause']} 条")
    elif m.get("chapter"):
        parts.append(m["chapter"])
    parts.append(f"(第{m.get('page', '?')}页)")
    return " ".join(parts)
