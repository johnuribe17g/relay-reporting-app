FROM node:22-alpine

WORKDIR /app
# Dependencies are installed in the image. docker-compose bind-mounts ./frontend over /app and keeps
# the image's node_modules with an anonymous volume (renewed by `up -V`).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
