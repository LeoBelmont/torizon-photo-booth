# Torizon Photo Booth — Arduino VENTUNO Q

Smile at the camera. The board photographs you, puts your face into a character portrait
— pharaoh, knight, samurai, astronaut — and fades it in over the live view. Everything
runs on the board: no cloud, no network calls, nothing written to disk.

This branch is the **Arduino VENTUNO Q** build, packaged as an **Arduino App Lab** App:
the face swap runs on the board's **Hexagon NPU**, and a native **Qt 6** panel replaces
the Weston + Chromium pair of the Jetson build. The Jetson/TensorRT version lives on
`main`; the two share no files here.

The same App is meant to run unchanged on the VENTUNO Q's stock Ubuntu image and on a
Torizon OS build for the board, which is the
[Works with Arduino](https://www.arduino.cc/pro/works-with-arduino/) story on Toradex
hardware.

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
| `docker-compose.yml` | The two containers for a board without the App Lab runtime. Keep it next to `app/`. |
| `scripts/` | `build-booth.sh`, `build-qt-ui.sh`, `export-app.sh`. |
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

## Running

### As an Arduino App

Copy `app/` to `/home/arduino/ArduinoApps/photo-booth`, or run `scripts/export-app.sh` and
import the zip in Arduino App Lab. Then press **Run**, or from a shell on the board:

```sh
arduino-app-cli app start ~/ArduinoApps/photo-booth
arduino-app-cli app logs  ~/ArduinoApps/photo-booth --follow
```

The panel needs the display to itself, so stop the desktop first with
`sudo systemctl stop display-manager`. To show the panel as a window inside a running
desktop session instead, set the `qt_ui` Brick's `QT_QPA_PLATFORM` variable to `wayland`.

### Without the App Lab runtime

The same two containers, from a plain compose file. Useful for bring-up, and for a Torizon
OS build of the board where `arduino-app-cli` is not installed yet.

```sh
scp -r app docker-compose.yml arduino@<board-ip>:~/photo-booth/
ssh arduino@<board-ip> 'sudo systemctl stop display-manager; cd photo-booth && docker compose up'
```

### Taking a photo without smiling

The booth API is published on port 8080, so `snap.sh` works from the board or from a PC:

```sh
./snap.sh --list                              # the nine effects
./snap.sh pharaoh                             # take one now
BOOTH=http://<board-ip>:8080 ./snap.sh --watch   # follow the state
```

`/api/state` reports `device: npu` once the sessions are up, `warming` before that.

## On Torizon OS

Build a release on the stock image with `arduino-app-cli app build --target ventunoq` and
install the `.ard` on the Torizon board. What that build has to provide: Docker 25 or newer,
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
