FROM python:3.11-slim

# Install Chrome and required dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    unzip \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY api.py .
COPY wsgi.py .

# Create directory for assignments file
RUN mkdir -p /app/data

# Environment variable to tell Chrome to run in headless mode
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Run as non-root user
RUN useradd -m myuser
RUN chown -R myuser:myuser /app
USER myuser

# Command to run the application
CMD ["python", "wsgi.py"]
