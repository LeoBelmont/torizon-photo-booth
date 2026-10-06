# The App Lab runtime, in a container

Arduino ships `arduino-app-cli` and `arduino-router` as Debian packages with systemd
units. That suits Arduino's own Linux image and not Torizon OS, whose rootfs is OSTree
based and has no apt. Running them from a container instead means an **Arduino App needs
nothing installed into the operating system**: Docker is the only requirement, and Torizon
is built on it.

```sh
docker compose -f runtime/compose.yml up -d
docker compose -f runtime/compose.yml exec arduino-app-cli arduino-app-cli app list
```

Apps then live in `/var/lib/arduino-apps/apps` on the host, and `arduino-app-cli app start`
brings up the App's containers exactly as it does on an Arduino board.

## The one thing to understand

The runtime does **not** run the App's containers inside itself. It talks to the host's
Docker socket and creates them as **siblings**. So every path it writes into a generated
compose file is a host path, while every host fact it resolves is read from inside the
runtime container. Those two views only agree if the container is wired for it:

| Mount | Why |
| --- | --- |
| `/var/run/docker.sock` | Creates the App's containers on the host. |
| `/etc/group`, `/etc/passwd` read-only | The runtime turns group names like `video` and `render` into numeric ids with a lookup **inside** this container. Without the host's database the App's containers get the wrong ids and lose access to the camera, the GPU and the NPU. |
| the apps, releases and data directories, **at identical paths** | The App folder is bind-mounted into its own container by the path the runtime saw. A different path inside would mount nothing. |
| `/sys` read-only | Device major numbers for the cgroup rules, and the device tree the board is identified from. |
| `/dev` | Flashing the sketch, the microcontroller's serial port, and the camera. |
| `/usr/share/qcom`, `/run/user/1000` | The runtime writes some mounts as "include this if the board has it" and tests for them here, so they must be visible at the same path. |

`$HOME` is pinned to `/var/lib/arduino-apps/home` rather than the host user's home, because
the runtime keeps downloaded models under it and hands that path to the App's containers to
mount. Keeping it inside a directory already mounted at an identical path makes it work
wherever the container runs.

The packages are unpacked rather than installed: their maintainer scripts drive systemd,
apt and user creation, none of which a container has. Only the binaries and the asset tree
are kept. `arduino-app-cli` refuses to run as root exactly as it does on a board, so the
entrypoint prepares the directories as root and then drops to uid 1000, which is `torizon`
on Torizon OS and `arduino` on the Arduino image.

## Verified

Built for amd64 and run against this PC's Docker, the containerized runtime created an App,
pulled the runtime image, and started the App's container as a host sibling. The container
showed `/app` bound to the real host path, `group_add` holding the host's own numeric ids
for video, render, audio and dialout, and the process running as uid 1000 rather than root.

## What it does not solve

Everything left is kernel and firmware, which no container can provide:

- the Hexagon NPU needs `/dev/fastrpc-cdsp*`, `/dev/dma_heap/system` and the DSP firmware
  under `/usr/share/qcom`;
- the panel needs `drm/msm` with Adreno 623 for hardware rendering;
- the microcontroller needs its serial port, `/dev/ttySTM0` on the VENTUNO Q.

Board identity is the one soft spot: the runtime reads the device tree `compatible` string
and expects `arduino,monza`. If a Torizon device tree reports something else, drop a
`platform.json` naming the board into the data directory, which is a host file the
container picks up.

## Settings

| Variable | Default | What |
| --- | --- | --- |
| `SERIAL_PORT` | `/dev/ttySTM0` | The microcontroller's port. Empty disables the MCU bridge. |
| `APP_UID` | `1000` | The user the runtime drops to. |
| `APP_HOME_DIR` | `/var/lib/arduino-apps/home` | Where custom models are kept. |
| `DAEMON_PORT` | `8800` | The REST API that App Lab on a PC talks to. |
| `ARDUINO_APP_CLI__APPS_DIR` | `/var/lib/arduino-apps/apps` | Where Apps live. Must be mounted at the same path. |

Pin the versions at build time with `--build-arg APP_CLI_VERSION=` and `ROUTER_VERSION=`.
