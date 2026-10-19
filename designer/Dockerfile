FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-impress \
        poppler-utils \
        fonts-liberation \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir --timeout 180 --retries 5 -r requirements.lock.txt
COPY pyproject.toml ./
COPY src ./src
COPY skills ./skills
COPY fonts /usr/local/share/fonts/voicedeck
RUN fc-cache -f

RUN useradd --create-home --uid 10001 designer \
    && mkdir -p /app/data \
    && chown -R designer:designer /app
ENV HOME=/home/designer DESIGNER_DATA_DIR=/app/data DESIGNER_SKILLS_DIR=/app/skills PYTHONPATH=/app/src
VOLUME /app/data
USER designer

EXPOSE 8090
CMD ["python", "-m", "designer", "serve"]
