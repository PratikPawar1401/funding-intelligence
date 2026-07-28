FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download NLP models (spaCy and NLTK)
RUN python -m spacy download en_core_web_lg
RUN python -m nltk.downloader wordnet omw-1.4

# Copy source code and config
COPY pyproject.toml .
COPY src/ ./src/
COPY data/ ./data/
COPY scraper_config/ ./scraper_config/
COPY prompts/ ./prompts/
COPY frontend/ ./frontend/

# Set Python path so 'foa_pipeline' can be imported
ENV PYTHONPATH=/app/src

# Create necessary directories for runtime data
RUN mkdir -p data/queues data/db data/raw data/normalised data/embeddings

# Expose FastAPI port
EXPOSE 8000

# Default command starts the API server
CMD ["uvicorn", "foa_pipeline.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
