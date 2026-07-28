# 施工规范审查 Agent 应用镜像。
# 模型不在镜像内：容器通过 OLLAMA_BASE_URL 连接宿主机的 Ollama 服务。
FROM python:3.11-slim

WORKDIR /app

# 最小系统依赖：
#   libgomp1      — ONNX Runtime 并行推理需要（rapidocr/onnxruntime 运行时必须）
#   libglib2.0-0  — 部分 PDF 图像处理库依赖
# 注意：不装 libxcb/libGL，因为我们用 opencv-python-headless，无需图形界面库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 先只拷 requirements 再装依赖：改代码时能命中 Docker 层缓存，不用重装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    # rapidocr-onnxruntime 会把 opencv 升级到 5.0，cv2 在那个版本里是残缺模块。
    # 解法：装完所有依赖后，把两个 opencv 变体全卸掉，再强制装回 4.11.0.86 headless。
    # 最后装的版本才是真正生效的版本——这是关键顺序。
    pip uninstall -y opencv-python opencv-python-headless || true && \
    pip install --no-cache-dir "opencv-python-headless==4.11.0.86" \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

ENV IN_DOCKER=1 \
    OLLAMA_BASE_URL=http://host.docker.internal:11434

EXPOSE 7860

CMD ["python", "app.py"]
