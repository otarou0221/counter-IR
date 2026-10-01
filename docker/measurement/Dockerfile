FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171 AS potree-converter-builder

ARG POTREE_CONVERTER_VERSION=2.1.3
ARG POTREE_CONVERTER_SHA256=508a0e286074653615ddcf0fb3f67d7dc44762f0312de8909bea47c00bedaa66
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates cmake curl g++ libtbb-dev make \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /source
RUN curl -fsSL \
      "https://github.com/potree/PotreeConverter/archive/refs/tags/${POTREE_CONVERTER_VERSION}.tar.gz" \
      -o potree-converter.tar.gz \
    && echo "${POTREE_CONVERTER_SHA256}  potree-converter.tar.gz" | sha256sum -c - \
    && tar -xzf potree-converter.tar.gz --strip-components=1 \
    && cmake -S . -B /build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --parallel 2

FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libtbb12 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=potree-converter-builder /build/PotreeConverter /usr/local/bin/PotreeConverter
COPY --from=potree-converter-builder /build/liblaszip.so /usr/local/lib/liblaszip.so
COPY --from=potree-converter-builder /build/licenses /usr/share/licenses/potree-converter
RUN ldconfig
WORKDIR /app
COPY docker/measurement/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY src/cardboard_counter_v2/__init__.py ./src/cardboard_counter_v2/__init__.py
COPY src/cardboard_counter_v2/common ./src/cardboard_counter_v2/common
COPY src/cardboard_counter_v2/measurement ./src/cardboard_counter_v2/measurement
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=3)"
CMD ["uvicorn", "cardboard_counter_v2.measurement.app:app", "--host", "0.0.0.0", "--port", "8002"]
