"""审查 Agent：基于 LangGraph 的 ReAct 循环，LLM 自主决定调用哪些工具。

流程：用户描述施工方案 → Agent 自行检索规范/校核强度 → 汇总成结构化审查报告。
"""
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from agent.tools import ALL_TOOLS
from config import OLLAMA_BASE_URL, OLLAMA_MODEL

SYSTEM_PROMPT = """你是土木工程施工方案审查专家。用户会给出施工方案描述或提问。

【强制规则】你自己的记忆不可靠，禁止凭记忆回答任何数值或条文。
第一步必须先调用工具获取依据，拿到工具结果后才允许撰写报告：
- 方案涉及混凝土强度 → 必须调用 check_concrete_strength
- 方案涉及钢筋 → 必须调用 check_steel_strength
- 需要规范条文依据 → 必须调用 search_spec
没有调用任何工具就直接回答 = 严重错误。

审查完成后，用中文输出结构化报告，格式：
## 审查结论
（合规 / 有问题 / 资料不足，一句话总结）

## 逐项审查
每项包含：
- 审查内容
- 规范依据（必须注明规范名称和条文号，来自工具返回的出处；查不到就明说，禁止编造）
- 判定与建议

## 风险提示
（红=违反强制性条文，橙=不满足一般规定，黄=建议优化）

重要原则：所有数值和条文依据必须来自工具返回结果，绝不凭记忆编造条文号。"""

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        llm = ChatOllama(model=OLLAMA_MODEL, temperature=0, base_url=OLLAMA_BASE_URL)
        _agent = create_react_agent(llm, ALL_TOOLS, prompt=SYSTEM_PROMPT)
    return _agent


def run_review(user_input: str) -> tuple[str, list[str]]:
    """执行审查。返回 (最终报告, 工具调用轨迹) —— 轨迹用于界面展示 Agent 的思考过程。"""
    agent = get_agent()
    trace: list[str] = []
    final = ""

    # 限制递归步数，防止 7b 模型陷入死循环
    result = agent.invoke(
        {"messages": [("user", user_input)]},
        config={"recursion_limit": 25},
    )
    for msg in result["messages"]:
        kind = getattr(msg, "type", "")
        if kind == "ai" and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                trace.append(f"🔧 调用工具 {tc['name']}({tc['args']})")
        elif kind == "tool":
            content = str(msg.content)
            trace.append(f"↩️ 工具返回：{content[:150]}{'…' if len(content) > 150 else ''}")
        elif kind == "ai" and msg.content:
            final = msg.content
    return final, trace
