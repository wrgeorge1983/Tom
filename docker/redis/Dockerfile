# Stage 1: Generate certificates
FROM alpine/openssl AS cert-generator
WORKDIR /certs
RUN openssl genrsa -out ca.key 2048 && \
    openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt -subj "/CN=Redis-Dev-CA" && \
    openssl genrsa -out redis.key 2048 && \
    openssl req -new -key redis.key -out redis.csr -subj "/CN=redis" && \
    openssl x509 -req -in redis.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out redis.crt -days 365 && \
    chmod 600 *.key && \
    rm redis.csr

# Stage 2: Redis with certificates
FROM redis:7.4-alpine3.21
COPY --from=cert-generator --chown="redis:redis" /certs /etc/redis/certs
EXPOSE 6380
CMD ["redis-server", "--tls-port", "6380", "--tls-cert-file", "/etc/redis/certs/redis.crt", "--tls-key-file", "/etc/redis/certs/redis.key", "--tls-ca-cert-file", "/etc/redis/certs/ca.crt", "--tls-auth-clients", "no"]
