FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY message_server.py .

# Expose the server port
EXPOSE 8765

CMD ["python", "message_server.py"]
