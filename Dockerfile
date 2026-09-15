# Pick the platform: tensorrt-orin or tensorrt-thor.
ARG TRT_IMAGE=tensorrt-orin:local
FROM ${TRT_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get -y update && apt-get install -y --no-install-recommends \
        python3 \
        python3-numpy \
        python3-opencv \
        opencv-data \
        python3-onnxruntime \
        wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/models

RUN wget -qO /app/models/emotion-ferplus-8.onnx \
       https://github.com/onnx/models/raw/main/validated/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx \
    && test -s /app/models/emotion-ferplus-8.onnx

COPY assets/det_10g.onnx /app/models/det_10g.onnx
COPY assets/w600k_r50.onnx /app/models/w600k_r50.onnx
COPY assets/inswapper_128.onnx /app/models/inswapper_128.onnx
COPY assets/inswapper_emap.npy /app/models/inswapper_emap.npy

# Generated characters, never real people.
COPY templates/ /app/templates/

WORKDIR /app
COPY booth/ /app/booth/
COPY effects/ /app/effects/

# Engines are GPU-specific and need a GPU to build, so they are
# compiled on first run into this volume, not baked in.
ENV TRT_ENGINE_DIR=/engines
VOLUME ["/engines"]

EXPOSE 8080
CMD ["python3", "-m", "booth.app"]
