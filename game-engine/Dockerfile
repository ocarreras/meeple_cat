FROM rust:1.83-slim AS builder

RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY Cargo.toml Cargo.lock* build.rs ./
COPY proto/ proto/
COPY src/ src/

RUN cargo build --release

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/target/release/meeple-game-engine /usr/local/bin/meeple-game-engine

EXPOSE 50051

CMD ["meeple-game-engine", "--port", "50051"]
