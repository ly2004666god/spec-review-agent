# 施工规范审查 Agent

面向土木工程场景的规范知识库 + 智能审查 Agent。基于本地大模型（Ollama + Qwen2.5），数据不出本机。

## 相比上一版（ai-construction-spec-agent）的升级

| 能力 | 旧版 | 本版 |
|---|---|---|
| 文档格式 | 仅文字版 PDF | PDF（文字/扫描自动 OCR）+ Word(.docx) |
| 表格 | 丢失/错乱 | pdfplumber 提取，转 Markdown 入库 |
| 切分方式 | 500 字递归硬切 | **按条文号切分**（6.3.1 级别），超长递归兜底 |
| 元数据 | 无 | 规范名/编号/条文号/章节/页码 |
| 检索 | 纯向量 | **混合检索**：条文号精确匹配 + 向量语义 |
| 出处 | 无 | 回答标注《规范》编号、条文号、页码 |
| 规范管理 | 单库混存 | 每规范独立库，可列表/删除/选范围 |
| Agent | 无（固定流程） | **LangGraph ReAct Agent**，自主调用工具 |
| 评测 | 无 | 自建评测集，量化检索命中率 |

## 技术栈

Python · LangChain / LangGraph · Ollama (qwen2.5 + nomic-embed-text) · FAISS · RapidOCR · PyMuPDF / pdfplumber / python-docx · Gradio

## 快速开始

### 方式一：本机直跑

```bash
pip install -r requirements.txt
ollama pull qwen2.5 && ollama pull bge-m3
python app.py
```

### 方式二：Docker 部署

```bash
# 前提：宿主机已装 Ollama 并 pull 好 qwen2.5 / bge-m3
docker compose up -d --build
```

容器只含应用，通过 `OLLAMA_BASE_URL=http://host.docker.internal:11434`
连接宿主机的 Ollama（应用与模型服务分离部署）。向量库挂载在宿主机
`./vector_stores`，容器重建数据不丢。

浏览器打开 http://127.0.0.1:7860

1. 「规范管理」页上传规范（PDF/docx），自动解析、OCR、按条文切分入库
2. 「规范问答」页提问，回答带条文出处
3. 「智能审查」页粘贴施工方案描述，Agent 自主检索规范、校核强度并生成审查报告

## 评测

```bash
python eval/run_eval.py
```

按已入库规范编辑 `eval/questions.json`（期望关键词 + 期望条文号），量化检索命中率。

## 项目结构

```
config.py            全局配置
ingest/loader.py     多格式解析（PDF/扫描OCR/docx）+ 表格提取
ingest/splitter.py   按条文号切分 + 元数据
store/manager.py     多规范向量库管理（registry.json 登记）
retrieval/retriever.py  混合检索（条文号精确 + 向量语义）
agent/tools.py       Agent 工具：检索规范 / 混凝土强度校核 / 钢筋强度查询
agent/review_agent.py   LangGraph ReAct 审查 Agent
app.py               Gradio 三页签界面
eval/                评测集与评测脚本
```
