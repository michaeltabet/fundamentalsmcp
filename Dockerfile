FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# cache (taxonomy sqlite + edgartools data) lands under $HOME — mount it
ENV HOME=/cache \
    EDGAR_MCP_TRANSPORT=streamable-http \
    EDGAR_MCP_PORT=8000
RUN mkdir -p /cache && chmod 777 /cache

EXPOSE 8000
USER 10001
ENTRYPOINT ["fundamentalsmcp"]
