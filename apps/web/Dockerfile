# syntax=docker/dockerfile:1
# NEXORA gateway: static SPA + reverse proxy to the private API, served by unprivileged Nginx.
ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.27-alpine

FROM ${NODE_IMAGE} AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx vite build \
 && node docker/csp.mjs dist/index.html > security-headers.conf

FROM ${NGINX_IMAGE}
# The base image's default site is replaced by our template (conf.d is writable by the nginx user).
RUN rm -f /etc/nginx/conf.d/default.conf
# Render only our variables (keeps nginx's own $variables intact) and expose the container's DNS
# resolver as ${NGINX_LOCAL_RESOLVERS} for runtime re-resolution of the API hostname.
ENV NGINX_ENVSUBST_FILTER="^(NEXORA_|NGINX_LOCAL_RESOLVERS$)" \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    NEXORA_API_UPSTREAM=api:8000
COPY --chown=root:root docker/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chown=root:root docker/10-nexora-gateway.envsh /docker-entrypoint.d/10-nexora-gateway.envsh
COPY --from=build --chown=root:root /web/security-headers.conf /etc/nginx/nexora/security-headers.conf
COPY --from=build --chown=root:root /web/dist /usr/share/nginx/html
EXPOSE 8080
STOPSIGNAL SIGQUIT
USER 101
