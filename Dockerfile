FROM python:3.12-slim

ARG INKSTITCH_VERSION=3.2.2
ARG INKSTITCH_ARCH=x86_64
ARG INKSTITCH_DOWNLOAD_URL=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_PATH=/data \
    INKSCAPE_PATH=inkscape \
    INKSTITCH_EXT_PATH=/root/.config/inkscape/extensions \
    INKSTITCH_BIN_PATH=/root/.config/inkscape/extensions/inkstitch/bin/inkstitch \
    GDK_BACKEND=x11

WORKDIR /service

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        imagemagick \
        inkscape \
        libdrm2 \
        libgtk-3-0 \
        libnss3 \
        libsm6 \
        libwayland-client0 \
        libwayland-cursor0 \
        libwayland-egl1 \
        libwayland-server0 \
        libxext6 \
        libxrender1 \
        libxtst6 \
        potrace \
        unzip \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p "${INKSTITCH_EXT_PATH}" \
    && if [ -z "${INKSTITCH_DOWNLOAD_URL}" ]; then \
        INKSTITCH_DOWNLOAD_URL="https://github.com/inkstitch/inkstitch/releases/download/v${INKSTITCH_VERSION}/inkstitch-${INKSTITCH_VERSION}-linux-${INKSTITCH_ARCH}.tar.xz"; \
    fi \
    && curl -fsSL "${INKSTITCH_DOWNLOAD_URL}" -o /tmp/inkstitch.tar.xz \
    && tar -xJf /tmp/inkstitch.tar.xz -C "${INKSTITCH_EXT_PATH}" \
    && rm /tmp/inkstitch.tar.xz \
    && inkscape --version \
    && convert -version \
    && potrace --version \
    && test -f "${INKSTITCH_BIN_PATH}" \
    && chmod +x "${INKSTITCH_BIN_PATH}" \
    && test -x "${INKSTITCH_BIN_PATH}" \
    && ! ldd "${INKSTITCH_BIN_PATH}" | grep "not found"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /data/input /data/output /data/temp /data/jobs

EXPOSE 8000

CMD ["uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
