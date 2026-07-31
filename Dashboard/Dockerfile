# Two stages so the deployment host never needs Node: the build happens in an
# image that is thrown away, and only the static output ships. `git pull &&
# docker compose up -d --build` is then the whole deploy on a box that has
# nothing but docker and git.
FROM node:25-alpine AS build
WORKDIR /app
# Copy the manifests first: this layer only rebuilds when dependencies change,
# so an edit to a component does not reinstall node_modules.
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Plain HTTP on purpose. TLS is terminated in front of this container -- by the
# Tailscale Funnel today, by certbot or Caddy on the aznet server later -- and
# putting it here too would mean re-issuing certificates inside the image.
EXPOSE 8080
