# syntax=docker/dockerfile:1
# Photo booth backend for the Arduino VENTUNO Q: the booth's Python unchanged, with the
# face swap on the Hexagon NPU through ONNX Runtime's QNN provider. Built on Arduino's
# QAIRT base image, which carries the fastrpc libraries and the DSP configuration
# wrapper (/qairt-entrypoint.sh) that App Lab's own NPU bricks use.
#
# Build from the repository root (the models live in assets/, FER+ is fetched):
#   docker buildx build --platform linux/arm64 -f Dockerfile.ventunoq \
#     -t lbornia/ventuno-demo-booth:latest --load .
# or scripts/build-booth-ventunoq.sh.

FROM --platform=linux/arm64 ghcr.io/arduino/app-bricks/qairt-common-base:0.13.0

USER root
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --root-user-action=ignore \
        "numpy>=2,<3" \
        "opencv-python-headless>=4.10,<5" \
        "onnxruntime>=1.24" \
        "onnxruntime-qnn>=2.6" \
        "onnx>=1.16"

RUN mkdir -p /app/models /cache && chown 1000:1000 /cache
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates \
    && wget -qO /app/models/emotion-ferplus-8.onnx \
       https://github.com/onnx/models/raw/main/validated/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx \
    && test -s /app/models/emotion-ferplus-8.onnx \
    && apt-get purge -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY assets/det_10g.onnx assets/inswapper_128.onnx assets/inswapper_emap.npy /app/models/
# The HTP compiler needs static shapes: pin the identity model's batch to 1.
COPY assets/w600k_r50.onnx /tmp/w600k_r50.onnx
RUN python3 -m onnxruntime.tools.make_dynamic_shape_fixed \
        --input_name input.1 --input_shape 1,3,112,112 \
        /tmp/w600k_r50.onnx /app/models/w600k_r50.onnx \
    && rm /tmp/w600k_r50.onnx

# Generated characters, never real people.
COPY templates/ /app/templates/

WORKDIR /app
COPY booth/ /app/booth/
COPY effects/ /app/effects/

# The QNN libraries and HTP skeletons come from the onnxruntime-qnn wheel, so the DSP
# must load the skeleton from there, not from the base image's older QAIRT.
ENV PYTHONUNBUFFERED=1 \
    ORT_THREADS=4 \
    EFFECT_PACK=/app/effects/pack.json \
    PORT=8080 \
    QNN_CACHE_DIR=/cache \
    ADSP_LIBRARY_PATH=/usr/local/lib/python3.13/site-packages/onnxruntime_qnn \
    CDSP_LIBRARY_PATH=/usr/local/lib/python3.13/site-packages/onnxruntime_qnn

EXPOSE 8080
ENTRYPOINT ["/qairt-entrypoint.sh"]
CMD ["python3", "-m", "booth.app"]
