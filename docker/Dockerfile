FROM python:3.11-slim

WORKDIR /app

# ── System deps + TA-Lib (compiled from source) ───────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev wget make autoconf && \
    wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && \
    cp /usr/share/autoconf/build-aux/config.guess . && \
    cp /usr/share/autoconf/build-aux/config.sub . && \
    ./configure --prefix=/usr && make && make install && \
    cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz && \
    rm -rf /var/lib/apt/lists/*

# ── Python deps (baked into image layer — fast container starts) ───────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App source ────────────────────────────────────────────────────────────────
COPY . .

EXPOSE 8000

# Production: no --reload (dev override is set in docker-compose.yml)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
