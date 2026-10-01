FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src \
    ORBBEC_SDK_DIR=/app/third_party/orbbec_sdk \
    ORBBEC_HELPER_PATH=/app/build/orbbec_ir_depth_stream
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docker/camera/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY native ./native
COPY third_party/orbbec_sdk ./third_party/orbbec_sdk
COPY src/cardboard_counter_v2/__init__.py ./src/cardboard_counter_v2/__init__.py
COPY src/cardboard_counter_v2/common ./src/cardboard_counter_v2/common
COPY src/cardboard_counter_v2/camera ./src/cardboard_counter_v2/camera
RUN mkdir -p build \
    && g++ -std=c++17 native/orbbec_ir_depth_stream.cpp \
      -I"$ORBBEC_SDK_DIR/SDK/include" \
      -L"$ORBBEC_SDK_DIR/SDK/lib" \
      -lOrbbecSDK -Wl,-rpath,"$ORBBEC_SDK_DIR/SDK/lib" -O2 \
      -o "$ORBBEC_HELPER_PATH"
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3)"
CMD ["uvicorn", "cardboard_counter_v2.camera.app:app", "--host", "0.0.0.0", "--port", "8001"]
