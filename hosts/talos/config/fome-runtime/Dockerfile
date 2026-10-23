# fome-mc pinned runtime for talos (Ubuntu 26.04 host; fome-mc pins Ubuntu 24.04 / Python 3.12).
# Base: the qualified agent-ee image agent-ee:ee466-gate-b29cead1, image ID
# sha256:d96f8e00a50a1bb6fab119ac8973a083af9373e2c9c235f3df20f655cfc3b5b7 (build.sh checks it).
# It already has fome-mc's KiCad 10.0.7~ubuntu24.04.1, ngspice 42+ds-3build1, poppler 24.02.0-1ubuntu9.10,
# python3-wxgtk4.0 4.2.1+dfsg-3build2 and Python 3.12. This adds only fome-mc toolchain/versions.toml's
# remaining apt pins, make, and uv 0.13.4 (proximal's binary). Same Ubuntu snapshot (20261015T000000Z).
# Canonical source: infra hosts/talos/config/fome-runtime/.
FROM agent-ee:ee466-gate-b29cead1
USER root
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      mupdf-tools=1.23.10+ds1-1build3 librsvg2-bin=2.58.0+dfsg-1ubuntu0.1 \
      ghostscript=10.02.1~dfsg1-0ubuntu7.9 make \
 && apt-mark hold mupdf-tools librsvg2-bin ghostscript \
 && rm -rf /var/lib/apt/lists/*
COPY uv /usr/local/bin/uv
LABEL org.opencontainers.image.title="fome-mc runtime (talos)" \
      infra.base="sha256:d96f8e00a50a1bb6fab119ac8973a083af9373e2c9c235f3df20f655cfc3b5b7" \
      infra.uv="0.13.4"
USER 10001
