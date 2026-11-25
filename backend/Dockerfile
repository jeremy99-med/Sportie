FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements-video.txt ./
ARG INSTALL_VIDEO_DEPS=false
# Video deps: OpenCV needs libgl1/libglib, and CPU-only torch avoids ~3 GB of GPU libraries.
RUN if [ "$INSTALL_VIDEO_DEPS" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && \
        rm -rf /var/lib/apt/lists/* && \
        pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir -r requirements-video.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

EXPOSE 8000
