FROM node:20-alpine

WORKDIR /app

RUN corepack enable

COPY package.json tsconfig.json ./
RUN pnpm install --frozen-lockfile=false

COPY src ./src

RUN pnpm build

EXPOSE 3003

CMD ["node", "dist/index.js"]
