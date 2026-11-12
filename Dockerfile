FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv
FROM python:3.14-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f
COPY --from=uv /uv /usr/local/bin/uv
COPY dist/requirements.txt dist/*.whl /tmp/distribution/
RUN uv pip sync --system --require-hashes /tmp/distribution/requirements.txt \
    && uv pip install --system --no-deps /tmp/distribution/*.whl \
    && rm -rf /tmp/distribution
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10001 worker && useradd --uid 10001 --gid worker --no-create-home worker \
    && mkdir /data && chown worker:worker /data
USER worker
WORKDIR /data
ENTRYPOINT ["python", "-m", "pontomaisoumenos"]
CMD ["serve"]
