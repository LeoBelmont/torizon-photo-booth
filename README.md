# Torizon Photo Booth — Arduino VENTUNO Q

Smile at the camera. The board photographs you, puts your face into a character portrait
— pharaoh, knight, samurai, astronaut — and fades it in over the live view. Everything
runs on the board: no cloud, no network calls, nothing written to disk.

This branch is the **Arduino VENTUNO Q** build, packaged as an **Arduino App Lab** App:
the face swap runs on the board's **Hexagon NPU**, and a native **Qt 6** panel replaces
the Weston + Chromium pair of the Jetson build. The Jetson/TensorRT version lives on
`main`; the two share no files here.

**Torizon OS is the target.** The board has no desktop there, which is what the panel
wants: it takes the display directly, with no compositor in the way. The same App also
runs on the VENTUNO Q's stock Ubuntu image, where the desktop has to be moved aside
first. Running unchanged on both is the
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

The panel draws straight to KMS, so whatever else is on the board must not hold the
display.

### On Torizon OS

The main target, and the simple case: no desktop, so nothing to move aside. If the image
starts the usual Weston container, stop that first.

```sh
scp -r app docker-compose.yml torizon@<board-ip>:~/photo-booth/
ssh torizon@<board-ip>
docker stop weston 2>/dev/null || true    # only if this image runs one
cd photo-booth && docker compose up
```

Torizon OS does not carry `arduino-app-cli` yet, so the compose file is the way in. Once
the runtime is packaged for it, the App Lab route below works there unchanged. What else
a Torizon build has to provide is listed under
[What a Torizon OS build needs](#what-a-torizon-os-build-needs).

### On the stock Ubuntu image

GDM owns the display whenever a monitor is attached, even sitting at the login screen, so
free it first:

```sh
sudo systemctl stop display-manager                 # for now
sudo systemctl set-default multi-user.target        # or for good
```

Then run it as an Arduino App. Copy `app/` to `/home/arduino/ArduinoApps/photo-booth`, or
run `scripts/export-app.sh` and import the zip in Arduino App Lab, then press **Run**, or:

```sh
arduino-app-cli app start ~/ArduinoApps/photo-booth
arduino-app-cli app logs  ~/ArduinoApps/photo-booth --follow
```

The compose file above works here too, with user `arduino`.

To leave the desktop running and show the panel as a window inside it, set the `qt_ui`
Brick's `QT_QPA_PLATFORM` to `wayland` rather than stopping GDM. The panel then renders
into the session's compositor through `/run/user/1000/wayland-0`.

### Taking a photo without smiling

The booth API is published on port 8080, so `snap.sh` works from the board or from a PC:

```sh
./snap.sh --list                              # the nine effects
./snap.sh pharaoh                             # take one now
BOOTH=http://<board-ip>:8080 ./snap.sh --watch   # follow the state
```

`/api/state` reports `device: npu` once the sessions are up, `warming` before that.

## What a Torizon OS build needs

Once `arduino-app-cli` is on the board, a release built on the stock image with
`arduino-app-cli app build --target ventunoq` installs with `app install`. What the
Torizon build has to provide: Docker 25 or newer,
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
