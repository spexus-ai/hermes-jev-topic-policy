# syntax=docker/dockerfile:1.7
FROM python:3.11-slim
RUN pip install --no-cache-dir 'uv>=0.8,<1'
WORKDIR /opt/hermes
COPY --from=hermes_core . /opt/hermes
RUN uv sync --frozen --extra messaging --no-dev \
    && useradd --uid 10001 --create-home hermes \
    && mkdir -p /var/lib/hermes && chown hermes:hermes /var/lib/hermes
ENV PATH="/opt/hermes/.venv/bin:$PATH" HERMES_HOME=/var/lib/hermes PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
CMD ["hermes", "gateway", "run"]
