# Dedicated image for the UModel schema uploader.
# Installs umodel_uploader/requirements.txt explicitly instead of relying on
# the devops_data_generator image's transitive dependencies (see CHANGELOG
# Phase 3). The uploader imports only stdlib + the alibabacloud_* packages
# listed in requirements.txt; it does not import devops_data_generator.

FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

COPY umodel_uploader/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY umodel_uploader ./umodel_uploader

RUN mkdir -p /app/logs
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

CMD ["python3", "umodel_uploader/umodel_batch_uploader.py"]
