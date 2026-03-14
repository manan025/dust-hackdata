FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    unzip \
    zip \
    build-essential \
    cmake \
    ninja-build \
    python3 \
    python3-pip \
    openjdk-17-jdk \
    golang-go \
    rustc \
    cargo \
    ruby-full \
    php-cli \
    composer \
    nodejs \
    npm \
    maven \
    gradle \
    linux-tools-common \
    linux-tools-generic \
    linux-tools-6.8.0-106-generic \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -o /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends dotnet-sdk-8.0 \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/run_in_container.sh /runner/run_in_container.sh
RUN chmod +x /runner/run_in_container.sh

WORKDIR /work
