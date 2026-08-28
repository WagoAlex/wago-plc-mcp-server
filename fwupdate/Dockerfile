FROM python:3.12-slim

RUN pip install --no-cache-dir httpx==0.27.*

WORKDIR /app
COPY fw_update.py .

ENTRYPOINT ["python", "fw_update.py"]
