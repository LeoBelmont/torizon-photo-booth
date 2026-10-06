# Torizon Photo Booth

Smile at the camera. The board photographs you, puts your face into a character portrait
(pharaoh, knight, samurai, astronaut …) and fades it in over the live view. The face swap
runs on the VENTUNO Q's Hexagon NPU; nothing is written to disk or uploaded.

Two Bricks do the work: `photo_booth` runs the booth backend (camera, smile trigger, face
swap, HTTP API) and `qt_ui` draws the panel on the display with Qt. The sketch mirrors the
booth state on the built-in LED. Without a USB camera the booth uses bundled portraits.
