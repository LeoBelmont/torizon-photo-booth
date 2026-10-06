// Torizon Photo Booth: the built-in LED follows the booth.
//
//   idle      off
//   aim       blinks faster as the smile meter fills
//   generate  fast blink while the NPU swaps the face
//   reveal    on
//   error     three short flashes, then off

#include "Arduino_RouterBridge.h"

volatile int state = 0;    // 0 idle, 1 aim, 2 generate, 3 reveal, 4 error
volatile int smile = 0;    // 0..100

void booth_state(int newState, int newSmile) {
    state = newState;
    smile = newSmile;
}

void led(bool on) {
    // Active low on UNO Q / VENTUNO Q built-in LEDs.
    digitalWrite(LED_BUILTIN, on ? LOW : HIGH);
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    led(false);
    Bridge.begin();
    Bridge.provide("booth_state", booth_state);
}

void loop() {
    unsigned long now = millis();
    switch (state) {
    case 1: {  // aim: period from 1000 ms (no smile) down to 150 ms (full)
        unsigned long period = 1000 - (850UL * smile) / 100;
        led((now / (period / 2)) % 2 == 0);
        break;
    }
    case 2:
        led((now / 80) % 2 == 0);
        break;
    case 3:
        led(true);
        break;
    case 4:
        led((now % 1000) < 600 && ((now % 1000) / 100) % 2 == 0);
        break;
    default:
        led(false);
    }
    delay(10);
}
