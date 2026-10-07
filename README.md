# Torizon Photo Booth — Arduino VENTUNO Q

Smile at the camera. The board photographs you, puts your face into a character portrait
— pharaoh, knight, samurai, astronaut — and fades it in over the live view. Everything
runs on the board: no cloud, no network calls, nothing written to disk.

This branch is the **Arduino VENTUNO Q** build, packaged as an **Arduino App Lab** App:
the face swap runs on the board's **Hexagon NPU**, and a native **Qt 6** panel replaces
the Weston + Chromium pair of the Jetson build. The Jetson/TensorRT version lives on
`main`; the two share no files here.

**The point of the demo** is that it was built as an Arduino App Lab App on the VENTUNO Q's
stock Ubuntu image, and the same App then runs on Torizon OS on the same board. That is the
[Works with Arduino](https://www.arduino.cc/pro/works-with-arduino/) story on Toradex
hardware: build it the Arduino way, ship it the Toradex way, without rewriting it.

Torizon is the target of the two. The board has no desktop there, which is what the panel
wants, since it takes the display directly with no compositor in the way. On the Ubuntu
image the desktop has to be moved aside first.

Running it on a board for the first time: `scripts/check-board.sh` reports whether that
board has what the demo needs, and says what degrades if something is missing.

## How it is put together

```
┌──────────────────────────── compose project of the App ────────────────────────────┐
│                                                                                    │
│  main (python-apps-base)      booth (qairt-common-base + booth/)   qt_ui (Qt 6)    │
│  app/python/main.py           camera · smile · face swap           panel, EGLFS    │
│  bricks/photo_booth           HTTP :8080  ◄── /api/state ──────────  BoothClient   │
│       │ polls /api/state           ▲      ◄── /preview.mjpg ───────  MjpegView     │
│       │ Bridge → LED               │ QNN (ONNX Runtime)                            │
│       ▼                            ▼                                               │
│  arduino-router → STM32       /dev/fastrpc-cdsp (Hexagon NPU), /dev/video* (USB)   │
└────────────────────────────────────────────────────────────────────────────────────┘
```

- **`photo_booth` Brick** runs the booth backend: camera, smile trigger, face swap, and
  the HTTP API. Its container builds on Arduino's `qairt-common-base` image, which carries
  the fastrpc libraries and the DSP configuration wrapper that App Lab's own NPU Bricks use.
- **`qt_ui` Brick** runs the panel, a Qt Quick port of the Jetson build's web page. It
  polls the same `/api/state`, shows the MJPEG preview, fades the photo in, and offers the
  gallery. It draws straight to KMS through EGLFS, so no compositor is involved. One
  behaviour differs on purpose: a gallery tap always wins over the reveal of the photo just
  taken, where the web page snapped back and read as the gallery being stuck.
- **The App's own Python and sketch** follow the booth state and mirror it on the built-in
  LED over the Bridge, so the microcontroller takes part in the demo.

## Measured on the board

ONNX Runtime 1.30 with `onnxruntime-qnn` 2.6, HTP fp16, against four CPU threads:

| Model | CPU | Hexagon NPU |
| --- | --- | --- |
| inswapper_128 (face swap) | 3274 ms | 595 ms |
| w600k_r50 (identity) | 157 ms | 29 ms |
| det_10g (SCRFD) | 73 ms | 20 ms |

End to end, started by `arduino-app-cli` with a C922 webcam: **0.73 s** per photo against
4.0 s on the CPU. The first start compiles the two graphs (3 s and 29 s); later starts load
them from the cache volume in about 1.5 s. The NPU's fp16 output is visually identical to
the fp32 CPU result (34 dB PSNR), unlike TensorRT fp16 on Jetson, which forced the swap to
stay fp32 there.

The Qt panel renders on the Adreno 623 through Mesa's freedreno driver at 60 fps.

Three things are easy to get wrong:

- The HTP backend opens `/dev/fastrpc-cdsp-secure` as well as `/dev/fastrpc-cdsp`. Without
  the second node it fails silently and everything falls back to the CPU, so `ortrun.py`
  checks that a QNN context was really written and says so when it was not.
- `ADSP_LIBRARY_PATH` must point at the `onnxruntime-qnn` package, so the DSP loads the
  skeleton matching that QNN version rather than the base image's older one.
- A Brick must not list the booth's port in its `brick_config.yaml`. The orchestrator would
  publish it on the App's main container as well, and the start fails on the clash.

## Layout

| Path | What |
| --- | --- |
| `app/` | The Arduino App: `app.yaml`, `python/`, `sketch/`, `bricks/photo_booth`, `bricks/qt_ui`. |
| `booth/` | The backend. `sources.py` camera, `smile.py` + `expression.py` trigger, `faceswap.py` the swap, `ortrun.py` the NPU/CPU runner, `app.py` state machine and HTTP server. |
| `qt-ui/` | The panel: `BoothClient`, `MjpegView`, `qml/Main.qml`, its `Dockerfile`, Torizon and Arduino marks. |
| `Dockerfile` | The booth image, on Arduino's `qairt-common-base`. |
| `docker-compose.yml` | The two containers on their own, for bring-up and debugging. Not the way the demo runs. |
| `runtime/` | The App Lab runtime (`arduino-app-cli`, `arduino-router`) as a container, so Torizon OS needs nothing installed into the rootfs. |
| `deploy/` | `compose.yml`, a standalone file that is the whole demo from a registry on a board with only Docker, and `Dockerfile.app`, which carries the App folder as an image so nothing has to be copied. |
| `scripts/` | `photo-booth.sh` to run the App on either board, `check-board.sh` to check a board before you try, `build-images.sh` to build and push everything, plus `build-booth.sh`, `build-qt-ui.sh`, `export-app.sh`. |
| `effects/`, `templates/` | The effect pack and the character portraits it names. |

## Building

The ONNX models are not in this repository; put them in `assets/` as for the Jetson build.
`inswapper_emap.npy` is tracked, the three `.onnx` files are not.

```sh
docker login                      # Docker Hub, once
PUSH=1 scripts/build-booth.sh     # lbornia/ventuno-demo-booth:latest
PUSH=1 scripts/build-qt-ui.sh     # lbornia/ventuno-demo-booth-ui:latest
```

Without `PUSH=1` the images stay local; `BOARD=arduino@<ip>` loads them onto a board over
SSH instead of going through a registry. Both build for arm64, under emulation on an x86 PC.

## Deploying it from a registry

The short version, for a board with nothing on it but Docker. Copy one file and run one
command; every piece, including the App folder itself, arrives as an image:

```sh
scp deploy/compose.yml torizon@<board>:~/
ssh torizon@<board> 'docker compose -f compose.yml up -d'
```

`deploy/compose.yml` is standalone, so that one file is the whole deployment.

Two things in it exist because of how a container sees the host. Docker masks
`/sys/firmware` by default, so the runtime cannot read the device tree and identifies no
board at all, which fails any App with a sketch on `Missing FQBN`; the services that need
the board therefore run with `systempaths=unconfined`. And a `platform.json` naming the
board is written as a fallback, for a device tree that reports something other than
`arduino,monza`. It covers the FQBN but not the microcontroller's reset line, so a device
tree that identifies the board properly is still the better answer.

Building the sketch needs the Arduino core and tools, which are fetched from
`downloads.arduino.cc` the first time. On a board with no network:

```sh
WITHOUT_SKETCH=1 docker compose -f compose.yml up -d
```

The App then runs as a Python-only App, which needs neither the FQBN nor the toolchain.
Everything works except the LED on the microcontroller.

That brings up the App Lab runtime, seeds the App from `ventuno-demo-app`, and starts it
through `arduino-app-cli`, which creates the App's own containers on the host daemon. The
App outlives the stack, so `docker compose -f deploy/compose.yml down` removes the runtime
and leaves the demo running.

To build and publish the images in the first place:

```sh
docker login
PUSH=1 scripts/build-images.sh            # or REGISTRY=<account> PUSH=1 scripts/build-images.sh
```

## Running

The demo runs as an **Arduino App** on both boards, from the same App folder and with the
same commands. The only thing that differs is where the App Lab runtime comes from: the
Arduino image has it installed, and on Torizon OS it runs from a container.

```sh
scripts/photo-booth.sh install
scripts/photo-booth.sh start
scripts/photo-booth.sh logs
scripts/photo-booth.sh stop
```

The script picks the right path for the board it is on, so there is nothing to change
between the two. Underneath, both are ordinary `arduino-app-cli` commands against
`app/`, and `scripts/photo-booth.sh cli <args>` passes anything else straight through.

The panel draws straight to KMS and needs the display to itself. On Torizon that is
already the case. On the Arduino image a desktop is running, so the script says what to do
about it rather than stopping it behind your back: either stop the desktop, or set the
`qt_ui` Brick's `QT_QPA_PLATFORM` to `wayland` and let the panel open as a window inside it.

### What happens on each board

On the **Arduino image**, `arduino-app-cli` is already installed, so the script uses it and
the App lands in `~/ArduinoApps/photo-booth`. App Lab on a PC sees the App too, so you can
open it, edit it and press Run.

On **Torizon OS**, nothing Arduino is installed in the rootfs, by design: no
`arduino-app-cli`, no `arduino-router`, no apt to add them with. The script brings up
`runtime/compose.yml` instead, which runs both from containers, and the App lands in
`/var/lib/arduino-apps/apps/photo-booth`. Everything after that is identical, including the
Bricks, the sketch and the Bridge to the microcontroller. Docker is the only thing the OS
has to provide. See [runtime/README.md](runtime/README.md) for how that container is wired,
and [what a Torizon build still needs](#what-a-torizon-os-build-needs) for the kernel side.

The script picks between the two by looking for `arduino-app-cli` on `PATH`. `RUNTIME=container`
forces the containerized one even where a host install exists, and `RUNTIME=host` requires
the installed one, so what is being demonstrated never depends on an accident of the image.

### Without App Lab at all

`docker-compose.yml` starts the booth and the panel on their own, with no runtime, no
Bricks, no sketch and no microcontroller. It is there for bring-up and for debugging the
two containers in isolation, not as the way to run the demo.

```sh
scp -r app docker-compose.yml torizon@<board-ip>:~/photo-booth/
ssh torizon@<board-ip> 'cd photo-booth && docker compose up'
```

### Taking a photo without smiling

The booth API is published on port 8080, so `snap.sh` works from the board or from a PC:

```sh
./snap.sh --list                              # the nine effects
./snap.sh pharaoh                             # take one now
BOOTH=http://<board-ip>:8080 ./snap.sh --watch   # follow the state
```

`/api/state` reports `device: npu` once the sessions are up, `warming` before that.

## What a Torizon OS build needs

With the runtime in a container (`runtime/`), the OS itself only has to provide Docker and
the kernel side. A release built on the stock image with
`arduino-app-cli app build --target ventunoq` then installs with `app install`: Docker 25 or newer,
`arduino-app-cli` and `arduino-router` with their uid 1000 user and groups, a device tree
that keeps the `arduino,monza` compatible string (or a `platform.json` override so the CLI
recognises the board), the `drm/msm` kernel driver with Adreno 623 for the panel, and the
Hexagon firmware under `/usr/share/qcom` with `/dev/fastrpc-cdsp*` for the NPU.

## Camera

USB (UVC) only, any webcam. Discovery uses the V4L2 `VIDIOC_QUERYCAP` ioctl rather than
picking the lowest-numbered node, so the board's own video codec nodes, `/dev/video32` and
`/dev/video33`, are skipped. `CAMERA_DEVICE` pins one node if several cameras are attached.

With no camera the booth falls back to bundled stock portraits and runs unattended, through
the same detector, so the whole path still gets exercised.

## Tests

```sh
R="docker run --rm -v $PWD:/w -w /w lbornia/ventuno-demo-booth:latest"

$R python3 test_smile.py                                   # smile trigger, bundled portraits
docker run --rm -v $PWD:/w -w /w --device /dev/video0 -v /sys:/sys:ro \
    lbornia/ventuno-demo-booth:latest python3 test_camera.py       # camera discovery
```
