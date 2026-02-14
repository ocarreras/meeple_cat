FROM node:22-alpine

WORKDIR /app

# Copy dependency files first for caching
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# Copy application code
COPY . .

# Set backend URL for build (rewrites get baked into build output)
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL

# Build the app
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
