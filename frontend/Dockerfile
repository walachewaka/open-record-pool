# Dockerfile for the frontend
#
# We use Docker's multi-stage builds feature to first build our Vue.js app, and
# then serve its static files with NGINX (#23). Building for production means the
# bundle is optimized and NGINX -- not the dev server -- serves it, so there are
# no root-owned files created in a mounted source folder (#18).
# See https://docs.docker.com/develop/develop-images/multistage-build/

# Build stage:
FROM node:16-alpine as build-stage
WORKDIR /app
# Install dependencies first so this layer is cached between source changes:
COPY package.json package-lock.json ./
RUN npm install
# Copy the rest of the frontend and build the production bundle:
COPY . .
# The backend URL is baked into the bundle at build time. Override with
# --build-arg VUE_APP_BACKEND_URL=... when building for a different host.
ARG VUE_APP_BACKEND_URL=http://localhost:5000/
ENV VUE_APP_BACKEND_URL=$VUE_APP_BACKEND_URL
RUN npm run build

# Production stage:
# Unprivileged NGINX (MOO-89): runs as non-root UID 101 and listens on 8080
# (see nginx.conf). Compose maps 127.0.0.1:8088:8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine as production-stage
# Serve the statically built files with NGINX:
COPY --from=build-stage /app/dist /usr/share/nginx/html
# SPA-aware config (history-mode routing fallback) + security headers:
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
