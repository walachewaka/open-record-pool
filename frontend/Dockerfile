# Dockerfile for the frontend
#
# We use Docker's multi-stage builds feature to first build our Vue.js app, and then serve its static files with NGINX.
# See https://docs.docker.com/develop/develop-images/multistage-build/
# NGINX serves our statically built files, since it's one of the most performance Web servers that is available.

# # Build stage:
# FROM node:16-alpine as build-stage
# RUN apk add --no-cache python3 make g++
# # Update npm:
# RUN npm install -g npm@latest
# # Install our dependencies:
# WORKDIR /app
# COPY package*.json ./
# RUN npm install
# COPY . .
# # Build our production-ready Vue.js app:
# RUN npm run build
# 
# # Production stage
# FROM nginx:1.22-alpine as production-stage
# # We copy the files from our first stage build into this final stage that forms our image:
# COPY --from=build-stage /app/dist /usr/share/nginx/html
# # We expose port 80
# EXPOSE 80
# CMD ["nginx", "-g", "daemon off;"]

FROM node:16-alpine

# Update npm and install vue cli:
RUN npm install --global \
    npm@8.16.0

# To avoid permission errors:
RUN npm config --global set cache /tmp

# ENV PATH /app/node_modules/.bin:$PATH
ENV VUE_APP_BACKEND_URL=http://localhost:5000

WORKDIR /app

# Copy the package.json files and install npm dependencies:
COPY package.json .
COPY package-lock.json .
ENV NODE_ENV=development
RUN npm install

COPY .eslintrc.js .

# Avoid permission denied errors:
RUN chown -R 1000:1000 "/root/.npm"

# Copy the frontend files in the Docker image
# Copy all the Vue.js and HTML files:
ADD src ./src
ADD public ./public

# We use npm to run the Vue.js project, for now:
# TODO: Use nginx for production
CMD ["npm", "run", "serve"]

