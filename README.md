# Torizon Photo Booth

Smile at the camera. The board photographs you, restyles the photo with a
diffusion model running locally on its GPU, and shows the before and after on
the attached display. An over-the-air update swaps the effect pack.

Everything runs on the board. No cloud, no network calls, nothing written to
disk -- the photo never leaves the device.

## Measured on an Orin Nano 8 GB

| | |
|---|---|
| Per photo, steady state | ~4.4 s |
| Diffusion model resident | 2.4 GB |
| Smile trigger | ~20 ms per detection |

Breakdown of a photo: sampling 3.0 s, TAESD decode 0.9 s, VAE encode 0.8 s.

## Running it

    docker compose up -d

Then the panel is on `http://<board>:8080`, and Chromium shows it fullscreen on
the attached display.

With no webcam plugged in the booth falls back to bundled stock portraits and
runs unattended -- the same detector, so the whole path still gets exercised.

## Layout

- `booth/sources.py` -- webcam, or stock portraits if there is no camera
- `booth/expression.py` -- FER+ over ONNX Runtime: is this face smiling
- `booth/smile.py` -- face detection plus the trigger's hysteresis
- `booth/effects.py` -- effect packs, the thing an OTA update replaces
- `booth/sdclient.py` -- talks to stable-diffusion.cpp's sd-server
- `booth/app.py` -- state machine and HTTP server
- `effects/pack.json` -- the effects themselves

## Camera

Discovery uses the V4L2 `VIDIOC_QUERYCAP` ioctl rather than picking the
lowest-numbered node. A UVC webcam typically claims two `/dev/video` nodes, one
of which carries only metadata and yields no frames while still opening cleanly,
so choosing by number is a coin flip. Verified against a real capture/metadata
pair: the metadata node is rejected and the capture node is used.

Two optional overrides, both empty by default:

- `CAMERA_DEVICE` -- pin one node, e.g. `/dev/video2`
- `CAMERA_HUB_PATTERN` -- pin a physical USB port, e.g.
  `platform-xhci-hcd.*.auto-usb-*`, for when several cameras are attached

## Tests

    docker build -t booth:local .
    R="docker run --rm -v $PWD:/w -w /w"
    E="FER_MODEL=/app/models/emotion-ferplus-8.onnx"

    # Smile trigger against the bundled portraits
    $R booth:local sh -c "$E python test_smile.py"

    # Camera discovery, needs real /dev/video nodes to mean anything
    $R --device /dev/video0 -v /sys:/sys:ro booth:local sh -c "$E python test_camera.py"

    # Live throughput through the detector
    $R --device /dev/video0 -v /sys:/sys:ro booth:local sh -c "$E python test_camera_live.py"
