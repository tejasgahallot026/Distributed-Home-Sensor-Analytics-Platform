FROM python:3.11-slim

WORKDIR /app

# Create templates dir
RUN mkdir -p templates

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x sensors/sensor_simulator.py

EXPOSE $PORT
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "1", "--timeout", "120", "app:create_app()"]
