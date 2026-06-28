# EcomIQ-RPA Docker Image
# Python 3.10 + Playwright + 桌面自动化依赖
FROM python:3.10-slim

LABEL maintainer="EcomIQ-RPA Team"
LABEL description="电商 RPA 数据采集与自动化运维平台"

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright 浏览器依赖
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    # 中文字体
    fonts-noto-cjk \
    # 工具
    curl \
    && rm -rf /var/lib/apt/lists/*

# 工作目录
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir DBUtils>=3.0 \
    && playwright install chromium --with-deps

# 复制项目源码
COPY src/ ./src/
COPY docs/ ./docs/

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src:/app/src/rpa
ENV FLASK_APP=src.main.app:app

# 端口
EXPOSE 5000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# 启动
CMD ["python", "-m", "src.main.app"]
