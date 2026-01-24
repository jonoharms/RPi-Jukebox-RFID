import logging
import threading

import jukebox.cfghandler
import jukebox.plugs as plugs
import jukebox.publishing
import jukebox.publishing.server
import jukebox.publishing.subscriber

from .led_controller import LedController

logger = logging.getLogger("jb.keyboard")
cfg = jukebox.cfghandler.get_handler("jukebox")

PINS = {"repeat": 0, "single": 1, "random": 2, "prev": 3, "play": 4, "next": 5}

class Keyboard(threading.Thread):
    """A thread for monitoring events and displaying on an the keyboard."""

    def __init__(self):
        super().__init__(name="keyboard")
        self.daemon = True
        self._keep_running = True
        self.status = {'repeat': 0, 'single': 0, 'random': 0, 'state': 'stop'}
        # self.listen_done = threading.Event()
        # self.action_done = threading.Event()

    def toggle_led(self, button: str, payload: dict):
        if payload[button] != self.status[button]:
            self.status[button] = payload[button]
            with LedController() as controller:
                if self.status[button] == "1":
                    controller.set_color(PINS[button], 0, 0, 50)
                else:
                    controller.set_color(PINS[button], 0, 0, 0)

    def run(self) -> None:
        """Main loop of the Keyboard thread."""
        logger.info("Starting Keyboard Thread")

        sub = jukebox.publishing.subscriber.Subscriber(
            "inproc://PublisherToProxy", ["playerstatus"]
        )

        while self._keep_running:
            topic, payload = sub.receive()
            if topic == "playerstatus":
                for button in ["repeat", "single", "random"]:
                    self.toggle_led(button, payload)
                if self.status["state"] != payload["state"]:
                    self.status["state"] = payload["state"]
                    with LedController() as controller:
                        if self.status["state"] == "stop":
                            controller.set_color(PINS["play"], 50, 0, 0)
                        elif self.status["state"] == "pause":
                            controller.set_color(PINS["play"], 50, 30, 0)
                        elif self.status["state"] == "play":
                            controller.set_color(PINS["play"], 0, 50, 0)
                        else:
                            controller.set_color(PINS["play"], 0, 0, 0)


        logger.info("Exiting  Thread")

    def stop(self):
        """Stop the Keyboard thread."""
        logger.info("Stopping Keyboard Thread")

        self._keep_running = False
        # self.listen_done.clear()
        # self.action_done.set()


keyboard: Keyboard


@plugs.initialize
def initialize():
    """Setup connection and trigger the Keyboard loop."""
    global keyboard
    logger.info("Executing initialize handler, starting Keyboard process.")
    keyboard = Keyboard()
    keyboard.start()


@plugs.atexit
def atexit(signal_id: int, **ignored_kwargs):
    global keyboard
    logger.info("Executing atexit handler, stopping Keyboard process.")
    keyboard.stop()
