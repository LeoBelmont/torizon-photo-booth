# Photo Booth Demo — How to run it

Smile at the camera and the board photographs you, puts your face into a
character portrait — pharaoh, knight, samurai, astronaut — and fades it in over
the live view. Everything runs on the Jetson: no cloud, no network calls, and
nothing is written to disk.

Everything runs on the board and shows on the attached display.

## Requirements

* **Jetson Orin** (Nano, NX or AGX) running **Torizon OS 7**
* A **display** connected to the board
* A **USB webcam** — any UVC camera. Plug it in before starting.
* **Internet on the board** for the first start — about **17 GB** to download
* About **25 GB free** on the board

## Steps

1. Download the attached **docker-compose.yml**.

2. Copy it to the board:

   ```bash
   scp docker-compose.yml torizon@<board-ip>:~/
   ```

3. Start it:

   ```bash
   ssh torizon@<board-ip>
   docker compose up -d
   ```

The first start downloads about 17 GB, so give it time. The demo then appears on
the display and keeps running, including after a reboot.

On a **brand new board the booth needs about five minutes** before it will take
a photo: it compiles the models for that board's GPU first, and the screen says
**"Warming up…"** until it is done. That happens once — the compiled models are
kept, so later restarts are immediate and a photo takes well under a second.

To stop it: `docker compose down`

## Placing the camera

This is the one thing worth getting right.

* Put the camera at **face height**, not on the desk pointing up.
* People should be **close** — head and shoulders filling the frame.
* Avoid a bright window directly behind the person.

The screen tells you when something is wrong: **"Come closer"** or **"Hold
still"**. If you see those, the booth is refusing to take a photo it knows will
come out badly.

## Using it

The screen shows the camera. Stand in front of it and smile.

* The bar along the bottom fills as you smile — hold it and the photo is taken
* The finished photo fades in over the live view, with the effect's name
* It fades back out on its own and the camera returns
* **Tap any photo** in the grid on the right to see it again

Each photo gets a different character, cycling through nine of them.

## Taking a photo without smiling

Useful for testing, or for someone who would rather not perform:

```bash
ssh torizon@<board-ip>
cd ~/photo-booth
./snap.sh --list        # the nine effects
./snap.sh pharaoh       # take one now
```

Someone still has to be in front of the camera — the booth needs a face to work
from, and will say `no face found to swap` if there isn't one.

## Privacy

Worth saying out loud to visitors, because it is true and it is the point:
photos are processed on the board, held in memory only, never written to disk
and never uploaded. Restarting the demo erases them.
