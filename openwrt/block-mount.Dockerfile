# Native-arch base like hostapd.Dockerfile: an amd64-only container runs apt
# under qemu on the ARM runner, where jammy's keyring parsing fails (NO_PUBKEY).
FROM debian:trixie
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    bison build-essential ca-certificates curl file flex gawk git gettext libncurses-dev \
    libssl-dev m4 patch python3 python3-setuptools rsync unzip wget zstd util-linux \
    && rm -rf /var/lib/apt/lists/*
