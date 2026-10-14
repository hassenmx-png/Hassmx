FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 fontconfig fonts-inter fonts-noto-cjk fonts-noto-cjk-extra curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* && fc-cache -f

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Voix française (Kokoro, open source, ~350 Mo)
RUN mkdir -p /app/models && \
    curl -L -o /app/models/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx && \
    curl -L -o /app/models/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

COPY engine.py app.py ./
COPY static ./static

ENV MODELS_DIR=/app/models \
    DATA_DIR=/data \
    INTER_DIR=/usr/share/fonts/opentype/inter \
    JP_FONT=/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
