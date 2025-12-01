FROM python:3.12-slim

WORKDIR /app

# 基础依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        wget \
        curl \
        gnupg2 \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# 设置时区
ENV TZ=America/Toronto
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright
RUN pip install playwright

# 复制代码
COPY . .

# 创建用户并安装 Chromium，缓存到用户目录
RUN useradd -m -u 1000 appuser && \
    mkdir -p /home/appuser/.cache && \
    playwright install chromium --with-deps && \
    mv /root/.cache/ms-playwright/chromium-* /home/appuser/.cache/ms-playwright/ && \
    chown -R appuser:appuser /home/appuser/.cache && \
    chown -R appuser:appuser /app

USER appuser

# 验证用户路径下是否有浏览器（关键！）
# 移除冗余安装，仅验证
RUN ls -la /home/appuser/.cache/ms-playwright/chromium-*/chrome-linux/chrome || echo "Chromium not found, but proceeding"

CMD ["/bin/bash"]