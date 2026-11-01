# syntax=docker/dockerfile:1
#
# DCSS webtiles server for the decision-ladder prototype.
#
# Adapted from nkhoit/dcss-webtiles (MIT). Differences:
#   - built without USE_DGAMELAUNCH, so wizard mode is available to the
#     dcss-api scenario builder (the same way dcss-api's own test server is built)
#   - runs crawl from its build tree instead of `make install`
#   - builds natively on arm64 (the upstream image is amd64-only)
#
# DCSS itself is GPLv2: https://github.com/crawl/crawl/blob/master/LICENSE

ARG UBUNTU_VERSION=24.04

FROM ubuntu:${UBUNTU_VERSION} AS builder

ARG CRAWL_VERSION=0.34.0
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf bison build-essential flex git ca-certificates \
    libncursesw5-dev libsqlite3-dev libz-dev pkg-config \
    binutils-gold libsdl2-image-dev libsdl2-mixer-dev libsdl2-dev \
    libfreetype-dev libpng-dev fonts-dejavu-core advancecomp pngcrush \
    python3 python3-yaml \
  && rm -rf /var/lib/apt/lists/*

RUN git clone --branch ${CRAWL_VERSION} --depth 1 https://github.com/crawl/crawl.git /crawl \
  && cd /crawl && git submodule update --init --depth 1

RUN cd /crawl/crawl-ref/source \
  && make -j"$(nproc)" WEBTILES=y \
  && find . -name '*.o' -delete \
  && rm -rf /crawl/.git /crawl/crawl-ref/source/contrib

FROM ubuntu:${UBUNTU_VERSION}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bzip2 python3-minimal python3-pip python3-yaml \
    ncurses-term locales-all locales sqlite3 libsqlite3-0 zlib1g libpcre3 liblua5.1-0 lsof \
  && pip3 install --break-system-packages tornado \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /crawl/crawl-ref/source /crawl
# crawl looks for settings/ and docs/ one level above its binary
COPY --from=builder /crawl/crawl-ref/settings /settings
COPY --from=builder /crawl/crawl-ref/docs /docs
RUN if ldd /crawl/crawl | grep -q 'not found'; then ldd /crawl/crawl; exit 1; fi

COPY config.py /crawl/webserver/config.py
COPY init.txt /crawl/settings/ladder-init.txt
COPY init-player.sh /crawl/util/ladder-init-player.sh
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh /crawl/util/ladder-init-player.sh

EXPOSE 8080
VOLUME /data
WORKDIR /crawl
ENTRYPOINT ["/entrypoint.sh"]
