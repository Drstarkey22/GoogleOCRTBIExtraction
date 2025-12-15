FROM python:3.11-slim-bookworm

# Install system dependencies (wkhtmltopdf for PDF generation)
RUN apt-get update && apt-get install -y wkhtmltopdf && rm -rf /var/lib/apt/lists/*

# Copy application code
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Set environment variables for Flask
ENV PORT=8080

# The entrypoint uses Gunicorn, which is recommended for production deployments
CMD ["gunicorn", "--bind", ":8080", "--timeout", "300", "main:app"]
