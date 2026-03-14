FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ARG KERNEL_REF=v6.8

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
    python3-dev \
    libdw-dev \
    libunwind-dev \
    flex \
    bison \
    pkg-config \
    libelf-dev \
    libtraceevent-dev \
    linux-tools-common \
    linux-tools-generic \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -o /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends dotnet-sdk-8.0 \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/perf_recommend.py /runner/perf_recommend.py
RUN python3 -m pip install --no-cache-dir requests

RUN git clone --depth 1 --branch ${KERNEL_REF} https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git /tmp/linux \
    && make -C /tmp/linux/tools/perf NO_JEVENTS=1 \
    && cp /tmp/linux/tools/perf/perf /usr/bin/perf \
    && rm -rf /tmp/linux

COPY scripts/run_in_container.sh /runner/run_in_container.sh
RUN chmod +x /runner/run_in_container.sh

WORKDIR /work
