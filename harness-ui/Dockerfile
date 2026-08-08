# syntax=docker/dockerfile:1
#
# One process: Next static export + Spring Boot jar + harness wheel in a venv.
#
# Build context is the **repo root** (needs root install.py). Invoke:
#
#   docker build -f harness-ui/Dockerfile --build-arg HARNESS_VERSION=v0.0.1 -t harness-ui .
#   cd harness-ui && docker compose up --build
#
# Harness-only smoke (no api/web required):
#
#   docker build -f harness-ui/Dockerfile --target runtime-base -t harness-ui:doctor .
#   ./harness-ui/scripts/smoke-doctor.sh

ARG HARNESS_VERSION=v0.0.1

# --- 1. web: Next static export → web/out/ -----------------------------------
FROM node:22-bookworm AS web
WORKDIR /src/web
COPY harness-ui/web/package.json harness-ui/web/package-lock.json ./
RUN npm ci
COPY harness-ui/web/ ./
RUN npm run build

# --- 2. maven: embed SPA, package Spring Boot jar ---------------------------
FROM maven:3.9-eclipse-temurin-21 AS maven
WORKDIR /src
COPY harness-ui/api/ ./api/
COPY --from=web /src/web/out/ ./api/src/main/resources/static/
# finalName override so the runtime stage always finds /out/app.jar
RUN mvn -f api/pom.xml -DskipTests -DfinalName=app package \
 && mkdir -p /out \
 && cp api/target/app.jar /out/app.jar

# --- 3a. runtime-base: JRE + Python 3.12 venv + pinned harness wheel --------
# Ubuntu noble ships Python 3.12 (jammy is 3.10 — too old for harness).
FROM eclipse-temurin:21-jre-noble AS runtime-base
ARG HARNESS_VERSION=v0.0.1
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv curl git \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    HARNESS_VERSION=${HARNESS_VERSION}
# install.py from repo root (build context). Always pin --tag; never bare --download.
COPY install.py /tmp/install.py
RUN python3 /tmp/install.py --download --tag=${HARNESS_VERSION} \
 && rm -f /tmp/install.py

# --- 3b. runtime: jar + adapter (default image) -----------------------------
FROM runtime-base AS runtime
WORKDIR /app
COPY --from=maven /out/app.jar /app/app.jar
COPY harness-ui/adapter/ /app/adapter/
ENV SERVER_PORT=8085 \
    DATA_DIR=/data
EXPOSE 8085
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
