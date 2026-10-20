FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RIFFNEL_WS=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY riffnel_memguard ./riffnel_memguard
COPY benchmark ./benchmark
COPY .streamlit ./.streamlit
RUN pip install --no-cache-dir ".[ui]"

RUN useradd --create-home app && mkdir /data && chown app /data
USER app
VOLUME /data
EXPOSE 8501

# `docker run IMAGE` starts the web UI; override the command to use the CLI, e.g.
#   docker run --rm IMAGE riffnel-memguard demo stale
CMD ["sh", "-c", "[ -f /data/memories.json ] || riffnel-memguard init --ws /data; exec riffnel-memguard ui --ws /data --address 0.0.0.0"]
