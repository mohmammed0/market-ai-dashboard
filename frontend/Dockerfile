FROM node:20-alpine AS build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./

ARG VITE_API_BASE_URL=/
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27-alpine

ENV MARKET_AI_SERVER_NAME=_
ENV MARKET_AI_BACKEND_UPSTREAM=backend:8000

COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
