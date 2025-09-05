# Use Python 3.12 with Ubuntu base - optimized for Google Cloud Run
FROM python:3.12-slim

# Install system dependencies and Chrome in one layer
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    unzip \
    xvfb \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver - version compatible with Chrome
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+') \
    && CHROMEDRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json" | \
    python3 -c "import sys, json; data=json.load(sys.stdin); versions=[v for v in data['versions'] if v['version'].startswith('$CHROME_VERSION')]; print(versions[-1]['version'] if versions else data['versions'][-1]['version'])") \
    && wget -O /tmp/chromedriver-linux64.zip "https://storage.googleapis.com/chrome-for-testing-public/$CHROMEDRIVER_VERSION/linux64/chromedriver-linux64.zip" \
    && unzip /tmp/chromedriver-linux64.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Copy application files (do NOT bake secrets into the image)
COPY basic_server.py ./
COPY pydanticai_gradechecker.py ./
COPY assignments.txt ./

# Set environment variables optimized for Google Cloud Run
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/bin/google-chrome

# Create non-root user for security (required for Google Cloud Run)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    mkdir -p /tmp/chrome-profiles && \
    chown -R appuser:appuser /tmp/chrome-profiles

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Start the application (Google Cloud Run will handle the display server)
CMD ["python", "basic_server.py"]