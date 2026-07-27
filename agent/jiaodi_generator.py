"""技术交底生成：复用本项目的向量检索能力，为指定工序生成结构化技术交底草稿。

与"规范问答/审查"的区别：问答是回答一个问题，交底是按固定六板块结构写一整篇文书。
但底层检索完全复用 retrieval.retrieve —— 单一数据源，不再单独维护一份规范库。
"""
from langchain_ollama import OllamaLLM

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from retrieval.retriever import build_context, retrieve

_llm = None


def _get_llm():
    """延迟创建 LLM，避免 import 时就连 Ollama。"""
    global _llm
    if _llm is None:
        _llm = OllamaLLM(model=OLLAMA_MODEL, temperature=0, base_url=OLLAMA_BASE_URL)
    return _llm


# 技术交底的固定六板块结构。写死保证输出规范、专业、好审。
JIAODI_STRUCTURE = """
一、工程概况
二、施工准备（人、机、料、场地）
三、施工工艺流程（分步骤详细说明）
四、质量要求（列出具体控制指标,必须依据规范）
五、安全注意事项
六、环保及文明施工
"""


def generate_jiaodi(process_name: str, params: str,
                    spec_ids: list[str] | None = None) -> tuple[str, str]:
    """
    为某工序生成技术交底草稿。
    process_name: 工序名，如"钻孔灌注桩"
    params:       工程参数，如"桩径1.2m,桩长40m,共32根"
    spec_ids:     限定检索的规范范围（None=全部已入库规范）
    返回：(交底草稿 Markdown, 检索到的规范出处文本)
    """
    # 第1步：检索。用"工序名+参数"作为查询，复用项目的混合检索。
    query = f"{process_name} {params} 施工工艺 质量 安全"
    docs = retrieve(query, spec_ids)

    if not docs:
        tip = (f"⚠️ 知识库中未检索到「{process_name}」相关规范，无法生成可靠交底。\n\n"
               "请先在「规范管理」页上传相关规范，或换用更准确的工序名称。")
        return tip, ""

    # 第2步：把检索到的规范拼成带出处编号的上下文。
    context = build_context(docs)

    # 第3步：组装 Prompt。核心约束：数值必须来自规范、不得编造。
    prompt = f"""你是一名经验丰富的公路桥梁施工技术负责人，请为以下工序编写一份规范的施工技术交底。

【工序名称】{process_name}
【工程参数】{params}

【必须参考的规范条文】（质量数值请严格依据以下条文，并在引用处标注编号如[1]，不得自行编造）：
{context}

【交底文档结构】请严格按以下六个板块组织，用 Markdown 的 ## 作为板块标题：
{JIAODI_STRUCTURE}

【写作要求】
1. 内容专业、条理清晰，面向施工班组，便于照做。
2. "质量要求"板块中的具体数值，必须来自上面给出的规范条文并标注出处编号；
   规范中没有的，注明"按设计及相关规范执行"，不要编造数字。
3. 结尾另起一行列出所引条文的完整出处。

现在开始编写这份技术交底："""

    draft = _get_llm().invoke(prompt)

    # 检索出处单独返回，方便界面展示"生成有依据"（可溯源）。
    sources = "\n".join(f"[{i}] {build_context([d]).splitlines()[0][4:]}"
                        for i, d in enumerate(docs, 1))
    return draft, sources
