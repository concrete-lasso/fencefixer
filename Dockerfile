FROM python:3.12-alpine

# Install iperf3
RUN apk update && apk add --no-cache iperf3

WORKDIR /app

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Consolidated Application
COPY app.py .

# Run application
CMD ["python", "app.py"]
