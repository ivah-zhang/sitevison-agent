FROM python:3.12-slim

# 示範相片的說明文字為中文，容器內建字型畫不出來，需另裝 CJK 字型
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

ENV CITF_DEMO_SEED=1 \
    CITF_DATA_DIR=/home/user/app/data \
    PYTHONUNBUFFERED=1

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
