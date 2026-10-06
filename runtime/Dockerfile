# syntax=docker/dockerfile:1
# The Arduino App Lab runtime in a container: arduino-app-cli and arduino-router.
#
# Arduino ships both as Debian packages with systemd units, which suits their own Linux
# image and not Torizon OS, where the rootfs is OSTree based and there is no apt. Running
# them from a container instead means an Arduino App needs nothing installed into the OS:
# Docker is the only requirement, and Torizon is built on it.
#
# The packages are unpacked rather than installed. Their maintainer scripts drive systemd,
# apt and user creation, none of which a container has or wants; only the two binaries and
# the asset tree matter.
#
# The one thing to understand before changing the compose file: arduino-app-cli does not
# run the App's containers inside this one. It talks to the host's Docker socket and
# creates them as siblings. Every path it writes into a generated compose file is
# therefore a *host* path, and every host fact it resolves (group ids, device numbers,
# whether a path exists) is read from inside this container. Both only agree if the
# directories are mounted at identical paths and /etc/group comes from the host. See
# compose.yml.

ARG DEBIAN_TAG=trixie-slim
FROM debian:${DEBIAN_TAG}

ARG APP_CLI_VERSION=0.14.0-rc.6
ARG ROUTER_VERSION=0.10.0
ARG TARGETARCH
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        socat \
        gpiod \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="${TARGETARCH:-arm64}"; \
    base_cli="https://github.com/arduino/arduino-app-cli/releases/download"; \
    base_rtr="https://github.com/arduino/arduino-router/releases/download"; \
    curl -fsSL -o /tmp/app-cli.deb "${base_cli}/v${APP_CLI_VERSION}/arduino-app-cli_${APP_CLI_VERSION}-1_${arch}.deb"; \
    curl -fsSL -o /tmp/router.deb  "${base_rtr}/v${ROUTER_VERSION}/arduino-router_${ROUTER_VERSION}-1_${arch}.deb"; \
    dpkg-deb -x /tmp/app-cli.deb /; \
    dpkg-deb -x /tmp/router.deb /; \
    rm -f /tmp/app-cli.deb /tmp/router.deb; \
    test -x /usr/bin/arduino-app-cli; \
    test -x /usr/bin/arduino-router; \
    # The data directory is bind-mounted from the host at run time, which would hide the
    # brick index and examples shipped in the package. Keep a pristine copy to seed it.
    mv /var/lib/arduino-app-cli /opt/arduino-app-cli-seed

COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# The runtime refuses to run as root, as it does on Arduino's own image, so the
# entrypoint drops to uid 1000 after preparing the directories. APP_UID overrides it.
ENV ARDUINO_APP_CLI__APPS_DIR=/var/lib/arduino-apps/apps \
    ARDUINO_APP_CLI__RELEASES_DIR=/var/lib/arduino-apps/releases \
    ARDUINO_APP_CLI__DATA_DIR=/var/lib/arduino-app-cli \
    ARDUINO_APP_CLI__REQUIRED_RUNTIMES=arduino/arduino-router \
    ROUTER_SOCKET=/run/arduino/arduino-router.sock \
    APP_UID=1000 \
    APP_HOME_DIR=/var/lib/arduino-apps/home

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["daemon"]
