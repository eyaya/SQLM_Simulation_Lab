# SQLM Simulation Lab - React/Vite client served by nginx, which also
# reverse-proxies /api and /health to the FastAPI container so the browser
# talks to a single origin (and never needs CORS).
FROM node:22-alpine AS build

WORKDIR /src

# npm ci needs both manifests and honours package-lock.json exactly.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Empty default => the client calls its own origin, which nginx proxies.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Substituted into the template by the nginx entrypoint at container start.
ENV BACKEND_ORIGIN=http://backend:8000 \
    NGINX_PORT=80

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --spider "http://127.0.0.1:${NGINX_PORT}/" || exit 1
