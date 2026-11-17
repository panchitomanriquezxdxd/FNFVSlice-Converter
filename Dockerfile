FROM python:3.12-slim

# Sin dependencias externas: solo se copia el paquete.
WORKDIR /app
COPY fnfconv ./fnfconv

RUN useradd -m app
USER app

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FNFCONV_MAX_UPLOAD_MB=512
EXPOSE 8080

# $PORT presente => modo web automático (escucha en 0.0.0.0, solo ZIPs subidos, límites y borrado automático)
CMD ["python", "-m", "fnfconv", "gui", "--no-browser"]
