FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (psycopg, qdrant-client[fastembed] 일부 빌드 의존성, healthcheck용 curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 (캐시 효율)
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install --no-cache-dir -e .

# 소스 복사 (M8: dashboard/ 제거)
COPY api /app/api
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY data /app/data
COPY db /app/db

EXPOSE 8000

# 컨테이너 외부에서 확인 가능한 health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/healthz || exit 1

# 부팅 시 alembic upgrade head 실행 후 uvicorn (abb 패턴)
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000"]
