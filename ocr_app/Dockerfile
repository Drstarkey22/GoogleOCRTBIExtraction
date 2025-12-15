FROM python:3.11-slim

# Install system dependencies (if any).  Document AI client libraries do not require additional packages.

# Copy application code
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Set environment variables for Flask
ENV PORT=8080

# The entrypoint uses Gunicorn, which is recommended for production deployments
CMD ["gunicorn", "--bind", ":8080", "main:app"]
