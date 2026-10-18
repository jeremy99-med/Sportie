FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements-video.txt ./
ARG INSTALL_VIDEO_DEPS=false
RUN if [ "$INSTALL_VIDEO_DEPS" = "true" ]; then \
        pip install --no-cache-dir -r requirements-video.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

EXPOSE 8000
