# syntax=docker/dockerfile:1
# Qt 6 photo booth panel, on plain Debian Forky with Qt and Mesa. Draws straight to
# KMS/DRM through EGLFS (no compositor). See examples/spinning-board for the rationale.
#
#   docker buildx build --platform linux/arm64 -t lbornia/ventuno-demo-booth-ui:latest --load qt-ui

ARG DEBIAN_TAG=forky-slim
ARG IMAGE_ARCH=arm64

FROM --platform=linux/${IMAGE_ARCH} debian:${DEBIAN_TAG} AS build
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake g++ make qt6-base-dev qt6-declarative-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . .
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build -j"$(nproc)" \
    && cmake --install build --prefix /opt/booth-ui

FROM --platform=linux/${IMAGE_ARCH} debian:${DEBIAN_TAG} AS runtime
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libqt6quick6 libqt6network6 \
        qml6-module-qtqml qml6-module-qtqml-workerscript \
        qml6-module-qtquick qml6-module-qtquick-controls qml6-module-qtquick-layouts \
        qml6-module-qtquick-templates qml6-module-qtquick-window \
        qt6-wayland \
        libegl1 libgles2 libgbm1 libegl-mesa0 libgl1-mesa-dri \
        libinput10 libudev1 libxkbcommon0 fontconfig fonts-dejavu-core \
        # JPEG decoding of the preview stream
        libqt6gui6 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/booth-ui /opt/booth-ui
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY kms.conf /etc/kms.conf
ENV LANG=C.UTF-8 \
    QT_QPA_PLATFORM=eglfs \
    QT_QPA_EGLFS_INTEGRATION=eglfs_kms \
    QT_QPA_EGLFS_KMS_ATOMIC=1 \
    QT_QPA_EGLFS_KMS_CONFIG=/etc/kms.conf \
    QT_QPA_EGLFS_HIDECURSOR=1
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
