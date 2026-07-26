"""全局配置：模型、路径、切分与检索参数。"""
import os
from pathlib import Path

# ---- 模型 ----
OLLAMA_MODEL = "qwen2.5:latest"        # 本地 LLM（7b）
EMBEDDING_MODEL = "bge-m3"   # 向量化模型（中文效果显著优于 nomic-embed-text）
# Ollama 服务地址：本机直跑用默认值；Docker 容器里通过环境变量
# 指到宿主机 http://host.docker.internal:11434
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# ---- 路径 ----
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"            # 放规范原始文件（PDF/docx）
STORE_DIR = BASE_DIR / "vector_stores"  # 每份规范一个独立向量库
REGISTRY_PATH = STORE_DIR / "registry.json"  # 已入库规范登记表

# ---- 文档解析 ----
OCR_MIN_TEXT_CHARS = 25   # 一页提取文字少于该值 → 视为扫描页，走 OCR
OCR_DPI = 200             # 扫描页渲染分辨率（越高越准也越慢）

# ---- 切分 ----
CHUNK_MAX_CHARS = 1200    # 单条文超过该长度时递归兜底切分
CHUNK_OVERLAP = 100

# ---- 检索 ----
RETRIEVE_K = 6            # 向量检索召回条数

for _d in (DATA_DIR, STORE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
