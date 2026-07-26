"""施工规范审查 Agent —— Gradio 界面。

三个页签：
1. 规范管理：上传（PDF/docx，自动 OCR 扫描页）、查看、删除
2. 规范问答：混合检索 + LLM 回答，标注条文出处
3. 智能审查：Agent 自主调用工具审查施工方案，展示调用轨迹
"""
import re
from pathlib import Path

import gradio as gr
from langchain_ollama import OllamaLLM

from agent.review_agent import run_review
from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from ingest.loader import load_document
from ingest.splitter import split_pages
from retrieval.retriever import build_context, retrieve
from store import manager

llm = OllamaLLM(model=OLLAMA_MODEL, temperature=0, base_url=OLLAMA_BASE_URL)

SPEC_CODE_RE = re.compile(r"(GB|JGJ|CJJ|JTG|TB|DL|SL|CECS)[/T]*\s*\d+[-—]\d{4}", re.I)


def _registry_table() -> list[list[str]]:
    reg = manager.list_specs()
    return [[sid, info["spec_name"], info["spec_code"],
             str(info["chunks"]), str(info.get("ocr_pages", 0))]
            for sid, info in reg.items()]


def _spec_choices() -> list[str]:
    return [f"{sid} | {info['spec_name']}" for sid, info in manager.list_specs().items()]


def upload_spec(file, spec_name, spec_code, progress=gr.Progress()):
    if not file:
        return "请先选择文件。", _registry_table(), gr.update(choices=_spec_choices())
    path = Path(file if isinstance(file, str) else file.name)

    if not spec_name.strip():
        spec_name = path.stem  # 没填名称就用文件名
    if not spec_code.strip():
        m = SPEC_CODE_RE.search(path.stem)  # 尝试从文件名里抠出 GB 50010-2010
        spec_code = m.group(0) if m else path.stem

    try:
        progress(0.1, desc="解析文档（扫描页会自动 OCR，较慢）…")
        pages = load_document(path)
        ocr_pages = sum(1 for p in pages if p["is_ocr"])

        progress(0.5, desc="按条文切分…")
        docs = split_pages(pages, spec_name.strip(), spec_code.strip())
        if not docs:
            return "未能从文档中提取到内容。", _registry_table(), gr.update(choices=_spec_choices())

        progress(0.7, desc=f"向量化 {len(docs)} 个块（本地模型，请耐心等待）…")
        manager.add_spec(docs, spec_name.strip(), spec_code.strip(),
                         path.name, ocr_pages)

        clause_cnt = sum(1 for d in docs if d.metadata.get("clause"))
        table_cnt = sum(1 for d in docs if d.metadata.get("type") == "table")
        msg = (f"✅ 入库成功：共 {len(docs)} 块（识别到条文 {clause_cnt} 块、"
               f"表格 {table_cnt} 块，OCR 页 {ocr_pages} 页）")
        return msg, _registry_table(), gr.update(choices=_spec_choices())
    except Exception as e:
        return f"❌ 入库失败：{e}", _registry_table(), gr.update(choices=_spec_choices())


def delete_spec(spec_id):
    if not spec_id.strip():
        return "请输入要删除的规范 ID（列表第一列）。", _registry_table(), gr.update(choices=_spec_choices())
    ok = manager.delete_spec(spec_id.strip())
    msg = "🗑️ 已删除。" if ok else "未找到该 ID。"
    return msg, _registry_table(), gr.update(choices=_spec_choices())


def answer_question(query, selected_specs):
    if not query.strip():
        return "请输入问题。"
    spec_ids = [s.split(" | ")[0] for s in (selected_specs or [])] or None
    docs = retrieve(query, spec_ids)
    if not docs:
        return "知识库为空或未检索到相关内容，请先在「规范管理」页上传规范。"

    context = build_context(docs)
    prompt = f"""你是土木工程规范专家。根据以下检索到的规范条文回答问题。

要求：
1. 只依据给出的条文回答，条文里没有的就说"检索到的内容中未涉及"，禁止编造
2. 引用时注明编号，如 [1]，并在结尾列出所引条文的完整出处

检索到的条文：
{context}

问题：{query}"""
    answer = llm.invoke(prompt)

    sources = "\n".join(f"[{i}] {build_context([d]).splitlines()[0][4:]}"
                        for i, d in enumerate(docs, 1))
    return f"{answer}\n\n---\n**检索出处**\n{sources}"


def agent_review(user_input):
    if not user_input.strip():
        return "请输入待审查的施工方案描述。", ""
    try:
        report, trace = run_review(user_input)
        return report or "（Agent 未生成最终报告，请重试或换个说法）", "\n".join(trace)
    except Exception as e:
        return f"❌ 审查出错：{e}", ""


with gr.Blocks(title="施工规范审查 Agent") as demo:
    gr.Markdown("# 🏗️ 施工规范审查 Agent\n"
                "多格式规范入库（自动 OCR）· 条文级检索 · Agent 智能审查")

    with gr.Tab("📚 规范管理"):
        with gr.Row():
            file_input = gr.File(label="上传规范（.pdf / .docx，扫描版自动 OCR）",
                                 file_types=[".pdf", ".docx"])
            with gr.Column():
                name_input = gr.Textbox(label="规范名称（选填，默认取文件名）",
                                        placeholder="混凝土结构设计规范")
                code_input = gr.Textbox(label="规范编号（选填，自动从文件名识别）",
                                        placeholder="GB 50010-2010")
                upload_btn = gr.Button("解析并入库", variant="primary")
        upload_status = gr.Textbox(label="状态", lines=2)
        spec_table = gr.Dataframe(
            headers=["ID", "规范名称", "编号", "块数", "OCR页数"],
            value=_registry_table(), label="已入库规范", interactive=False)
        with gr.Row():
            del_input = gr.Textbox(label="删除：输入规范 ID", scale=3)
            del_btn = gr.Button("删除", scale=1)

    with gr.Tab("💬 规范问答"):
        spec_filter = gr.CheckboxGroup(choices=_spec_choices(),
                                       label="检索范围（不选=全部规范）")
        qa_input = gr.Textbox(label="问题", lines=2,
                              placeholder="例如：梁的纵向受力钢筋最小配筋率是多少？ 或：6.3.1 条内容是什么？")
        qa_btn = gr.Button("检索并回答", variant="primary")
        qa_output = gr.Markdown(label="回答")

    with gr.Tab("🤖 智能审查"):
        gr.Markdown("输入施工方案描述，Agent 会**自主决定**检索哪些规范、做哪些校核。")
        review_input = gr.Textbox(
            label="施工方案描述", lines=5,
            placeholder="例如：某桥梁墩身采用 C25 混凝土，纵筋 HRB400，保护层厚度 30mm，"
                        "跨径 30m，请审查混凝土强度等级是否满足要求。")
        review_btn = gr.Button("开始智能审查", variant="primary")
        review_output = gr.Markdown(label="审查报告")
        trace_output = gr.Textbox(label="Agent 工具调用轨迹（展示思考过程）", lines=8)

    upload_btn.click(upload_spec, [file_input, name_input, code_input],
                     [upload_status, spec_table, spec_filter])
    del_btn.click(delete_spec, [del_input],
                  [upload_status, spec_table, spec_filter])
    qa_btn.click(answer_question, [qa_input, spec_filter], [qa_output])
    review_btn.click(agent_review, [review_input], [review_output, trace_output])

if __name__ == "__main__":
    import os
    if os.environ.get("IN_DOCKER"):
        # 容器里必须监听 0.0.0.0 外部才能访问，也没有浏览器可弹
        demo.launch(server_name="0.0.0.0", server_port=7860)
    else:
        demo.launch(inbrowser=True)  # 本机直跑：自动打开浏览器
