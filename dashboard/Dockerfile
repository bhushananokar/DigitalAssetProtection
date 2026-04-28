FROM node:20-alpine

WORKDIR /app

RUN corepack enable

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
