# Agora — imagem do servidor. Em produção a cifra usa o pacote cryptography (obrigatório quando AGORA_AMBIENTE=producao).
FROM python:3.13-slim
ARG COM_CRYPTOGRAPHY=1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AGORA_HOST=0.0.0.0 AGORA_PORTA=8765 AGORA_DB=/dados/agora.db \
    AGORA_EBOOKS_DIR=/dados/ebooks
RUN if [ "$COM_CRYPTOGRAPHY" = "1" ]; then pip install --no-cache-dir "cryptography>=43,<51"; fi
RUN python3 -c "import cryptography" || echo "AVISO: imagem sem cryptography; só serve para desenvolvimento"
WORKDIR /srv/agora
COPY server ./server
COPY app ./app
COPY site ./site
RUN useradd --system --uid 10001 agora && mkdir -p /dados/ebooks /backups && chown -R agora /dados /backups
USER agora
VOLUME ["/dados"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=4).status==200 else 1)"
CMD ["python3", "server/server.py"]
