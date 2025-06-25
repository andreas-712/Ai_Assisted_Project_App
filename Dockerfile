# Use a smaller base image for production
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source code
COPY . .

# Cloud Run injects the PORT environment variable.
# Gunicorn binds to the port specified by the PORT env var.
# The 'app:create_app()' part tells Gunicorn to import the 'create_app' function
# from 'app.py' and call it to get the Flask app instance.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 'app:create_app()'
# --workers 1: Often sufficient for Cloud Run as concurrency is handled by Cloud Run itself
# --threads 8: Good for handling multiple concurrent requests per worker
# --timeout 0: Prevents Gunicorn from timing out long-running requests (Cloud Run has its own timeout)