FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY island_traders/ island_traders/
COPY config/ config/
COPY README.md .
COPY RULES.md .

RUN pip install --no-cache-dir -e ".[server]"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/rooms')" || exit 1

CMD ["uvicorn", "island_traders.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--ws", "wsproto"]
