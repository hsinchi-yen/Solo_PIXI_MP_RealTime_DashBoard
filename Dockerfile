# Stage 1: install dependencies and build wheels
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements-prod.txt .
RUN pip install --no-cache-dir --user -r requirements-prod.txt

# Stage 2: runtime image
FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

COPY app/      ./app/
COPY frontend/ ./frontend/
COPY config/   ./config/

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
