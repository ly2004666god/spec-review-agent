"""Agent 可调用的工具集。

设计原则：工具做确定性的事（查库、查表、算数），LLM 只负责决策和组织语言。
混凝土强度等常用设计值直接内置成数据表（来源 GB 50010-2010 表 4.1.4），
比让 LLM 回忆数字可靠得多——这正是"工具调用"的价值。
"""
from langchain_core.tools import tool

from ingest.splitter import format_source
from retrieval.retriever import retrieve

# GB 50010-2010 表4.1.4-1/2：混凝土轴心抗压/抗拉强度设计值 (N/mm²)
CONCRETE_DESIGN = {
    "C15": {"fc": 7.2, "ft": 0.91}, "C20": {"fc": 9.6, "ft": 1.10},
    "C25": {"fc": 11.9, "ft": 1.27}, "C30": {"fc": 14.3, "ft": 1.43},
    "C35": {"fc": 16.7, "ft": 1.57}, "C40": {"fc": 19.1, "ft": 1.71},
    "C45": {"fc": 21.1, "ft": 1.80}, "C50": {"fc": 23.1, "ft": 1.89},
    "C55": {"fc": 25.3, "ft": 1.96}, "C60": {"fc": 27.5, "ft": 2.04},
    "C65": {"fc": 29.7, "ft": 2.09}, "C70": {"fc": 31.8, "ft": 2.14},
    "C75": {"fc": 33.8, "ft": 2.18}, "C80": {"fc": 35.9, "ft": 2.22},
}

# GB 50010-2010 表4.2.3-1：普通钢筋抗拉强度设计值 (N/mm²)
STEEL_DESIGN = {
    "HPB300": 270, "HRB400": 360, "HRBF400": 360,
    "RRB400": 360, "HRB500": 435, "HRBF500": 435,
}

# 常见构件的最低混凝土强度等级要求（GB 50010-2010 第4.1.2条简化）
MIN_GRADE_BY_MEMBER = {
    "素混凝土": "C15",
    "钢筋混凝土": "C20",
    "预应力混凝土": "C30",
}


@tool
def search_spec(query: str) -> str:
    """在已入库的规范知识库中检索相关条文。输入检索问题（可含条文号如 6.3.1），返回带出处的条文内容。"""
    docs = retrieve(query)
    if not docs:
        return "知识库中未检索到相关条文（可能尚未上传相关规范）。"
    parts = []
    for doc in docs[:6]:
        parts.append(f"出处：{format_source(doc)}\n内容：{doc.page_content[:600]}")
    return "\n\n".join(parts)


@tool
def check_concrete_strength(grade: str, member_type: str = "钢筋混凝土") -> str:
    """校核混凝土强度等级。输入强度等级(如 C30)和构件类型(素混凝土/钢筋混凝土/预应力混凝土)，
    返回该等级的抗压/抗拉设计值，并判断是否满足规范最低等级要求。"""
    grade = grade.upper().strip()
    if grade not in CONCRETE_DESIGN:
        return f"未知强度等级 {grade}，支持范围 C15~C80。"
    d = CONCRETE_DESIGN[grade]
    lines = [f"{grade}：轴心抗压强度设计值 fc = {d['fc']} N/mm²，"
             f"轴心抗拉强度设计值 ft = {d['ft']} N/mm²（GB 50010-2010 表4.1.4）"]

    min_grade = MIN_GRADE_BY_MEMBER.get(member_type)
    if min_grade:
        ok = int(grade[1:]) >= int(min_grade[1:])
        verdict = "满足" if ok else "不满足"
        lines.append(f"{member_type}构件最低要求 {min_grade}（GB 50010-2010 第4.1.2条），"
                     f"{grade} {verdict}要求。")
    return "\n".join(lines)


@tool
def check_steel_strength(steel_type: str) -> str:
    """查询钢筋抗拉强度设计值。输入钢筋牌号，如 HRB400、HPB300。"""
    key = steel_type.upper().strip()
    if key not in STEEL_DESIGN:
        return f"未知钢筋牌号 {key}，支持：{', '.join(STEEL_DESIGN)}。"
    return (f"{key} 抗拉强度设计值 fy = {STEEL_DESIGN[key]} N/mm²"
            f"（GB 50010-2010 表4.2.3）")


ALL_TOOLS = [search_spec, check_concrete_strength, check_steel_strength]
