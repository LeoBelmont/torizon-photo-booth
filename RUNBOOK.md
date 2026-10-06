# Photo Booth on the Arduino VENTUNO Q — how to run it

Smile at the camera and the board photographs you, puts your face into a character
portrait — pharaoh, knight, samurai, astronaut — and fades it in over the live view. The
face swap runs on the board's Hexagon NPU: no cloud, no network calls, and nothing is
written to disk.

## Requirements

* **Arduino VENTUNO Q**, on its stock Ubuntu image
* A **display** on the HDMI output
* A **USB webcam**, any UVC model. Plug it in before starting.
* **Internet on the board** for the first start, about 2.5 GB of container images
* About **6 GB free** on the board

## Starting it

The App is installed at `/home/arduino/ArduinoApps/photo-booth`. From Arduino App Lab,
open it and press **Run**. From a shell on the board:

```bash
sudo systemctl stop display-manager     # the panel needs the display to itself
arduino-app-cli app start ~/ArduinoApps/photo-booth
```

The booth appears on the display and keeps running. To stop it:

```bash
arduino-app-cli app stop ~/ArduinoApps/photo-booth
```

To have it come up on its own after a power cut, enable **Run at Startup** in App Lab, and
make the desktop stay out of the way with
`sudo systemctl set-default multi-user.target`. `systemctl start display-manager` brings
the desktop back when you want it.

## First start

The first start compiles the two models for this board's NPU and takes about **35 seconds**,
with **"Warming up…"** on screen until it is done. The compiled graphs are kept in a Docker
volume, so later starts are ready in a second or two and a photo then takes well under a
second.

## Placing the camera

This is the one thing worth getting right.

* Put the camera at **face height**, not on the desk pointing up.
* People should be **close**, head and shoulders filling the frame.
* Avoid a bright window directly behind the person.

The screen says when something is wrong: **"Come closer"** or **"Hold still"**. If you see
those, the booth is refusing to take a photo it knows will come out badly.

## Using it

The screen shows the camera. Stand in front of it and smile.

* The bar along the bottom fills as you smile; hold it and the photo is taken.
* The finished photo fades in over the live view, with the effect's name.
* It fades back out on its own and the camera returns.
* **Tap any photo** in the grid on the right to see it again, at any time.

Each photo gets a different character, cycling through nine of them. The built-in LED on
the board follows along: it blinks faster as the smile meter fills, flickers while the NPU
works, and stays on while the photo is shown.

## Taking a photo without smiling

Useful for testing, or for someone who would rather not perform:

```bash
ssh arduino@<board-ip>
./snap.sh --list        # the nine effects
./snap.sh pharaoh       # take one now
./snap.sh --watch       # follow what the booth is doing
```

Someone still has to be in front of the camera: the booth needs a face to work from, and
says `no face found to swap` if there is not one. `./snap.sh pharaoh --force` skips even
that check.

## If something looks wrong

| What you see | What to do |
| --- | --- |
| Black screen, no panel | The desktop has the display. `sudo systemctl stop display-manager`, then restart the App. |
| "Warming up…" for more than a minute | `arduino-app-cli app logs ~/ArduinoApps/photo-booth --tail 40`. If it says the NPU was not reached, the booth is on the CPU and photos take about 4 s. |
| "Waiting for a face" with a camera plugged in | Check the camera is a UVC model and appears as `/dev/video0`. The board's own `/dev/video32` and `/dev/video33` are codecs, not cameras. |
| Photos take about 4 s | The face swap fell back to the CPU. The logs name the reason. |

## Privacy

Worth saying out loud to visitors, because it is true and it is the point: photos are
processed on the board, held in memory only, never written to disk and never uploaded.
Stopping the demo erases them.
