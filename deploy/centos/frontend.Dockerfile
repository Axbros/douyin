FROM node:24-alpine AS builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.28-alpine
COPY deploy/centos/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
