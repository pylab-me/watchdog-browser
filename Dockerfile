# --- 第一阶段：构建阶段 (Builder) ---
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 1. 首先拷贝 setup.py 以利用 Docker 缓存
COPY setup.py .
# 创建一个空的 src 目录，因为 setup.py 中定义了 package_dir
RUN mkdir -p src/watchdog_browser && touch src/watchdog_browser/__init__.py

# 2. 安装依赖 (包括 Playwright)
RUN pip install --no-cache-dir ".[browser]"

# 3. 拷贝实际的源代码并安装项目
COPY . .
RUN pip install --no-cache-dir .


# --- 第二阶段：运行阶段 (Final) ---
FROM python:3.14-slim

# 注入环境变量，禁用交互并确保路径正确
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# 合并运行，确保 apt 缓存不在镜像层中残留
RUN playwright install-deps chrome && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /root/.cache/ms-playwright/downloading

# 预下载浏览器内核
RUN playwright install chrome

CMD ["watchdog-browser-worker"]