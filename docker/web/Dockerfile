FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171 AS potree-assets
ARG POTREE_VERSION=1.8.2
ARG POTREE_SHA256=c140a8bce0ce129de762fbc0fd3ba7c21120ffd36d423dd2755abb39f32aebe5
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /assets
RUN curl -fsSL \
      "https://github.com/potree/potree/releases/download/${POTREE_VERSION}/Potree_${POTREE_VERSION}.zip" \
      -o potree.zip \
    && echo "${POTREE_SHA256}  potree.zip" | sha256sum -c - \
    && unzip -q potree.zip \
    && mkdir -p /out/build /out/libs \
    && cp -a "Potree_${POTREE_VERSION}/build/potree" /out/build/ \
    && for library in jquery spectrum jquery-ui other tween d3 proj4 openlayers3 i18next jstree plasio three.js; do \
         cp -a "Potree_${POTREE_VERSION}/libs/${library}" /out/libs/; \
       done \
    && cp "Potree_${POTREE_VERSION}/LICENSE" /out/LICENSE

FROM nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=potree-assets /out /usr/share/nginx/html/vendor/potree
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/nginx-health || exit 1
CMD ["nginx", "-g", "daemon off;"]
