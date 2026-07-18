
FROM debian:bookworm-slim AS builder

COPY --from=bitnami/kubectl:latest /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/kubectl

RUN kubectl version --client


FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/bin/kubectl /usr/local/bin/kubectl

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
