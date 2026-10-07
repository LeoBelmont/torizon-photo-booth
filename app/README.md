# Torizon Photo Booth

Smile at the camera. The board photographs you, puts your face into a character portrait
(pharaoh, knight, samurai, astronaut …) and fades it in over the live view. The face swap
runs on the VENTUNO Q's Hexagon NPU; nothing is written to disk or uploaded.

Two Bricks do the work: `photo_booth` runs the booth backend (camera, smile trigger, face
swap, HTTP API) and `qt_ui` draws the panel on the display with Qt. The sketch mirrors the
booth state on the built-in LED. Without a USB camera the booth uses bundled portraits.

## Dependencies

There is no `requirements.txt`. The only third-party package this App uses is `requests`,
which Arduino's Python runtime image already ships, and declaring it would make the first
start reach PyPI. Boards with no network could not start at all. Add one back if the App
grows a dependency the image does not provide, and note that an offline board will then
need a wheel cache.
