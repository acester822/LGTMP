FROM python:3.12-slim

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false exporter

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ntopng_exporter.py .

USER exporter

EXPOSE 9101

ENTRYPOINT ["python", "-u", "ntopng_exporter.py"]
