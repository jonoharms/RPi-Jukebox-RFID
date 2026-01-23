import logging
import threading

import jukebox.cfghandler
import jukebox.plugs as plugs
import jukebox.publishing
import jukebox.publishing.server
import jukebox.publishing.subscriber

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306

logger = logging.getLogger("jb.oled")
cfg = jukebox.cfghandler.get_handler("jukebox")


class OLED(threading.Thread):
    """A thread for monitoring events and displaying on an OLED."""

    def __init__(self):
        super().__init__(name="oled")
        self.daemon = True
        self._keep_running = True
        self.serial = i2c(port=1, address=0x3C)
        self.device = ssd1306(self.serial)
        # self.listen_done = threading.Event()
        # self.action_done = threading.Event()

    def run(self) -> None:
        """Main loop of the OLED thread."""
        logger.info("Starting OLED Thread")

        sub = jukebox.publishing.subscriber.Subscriber(
            "inproc://PublisherToProxy", ["playerstatus"]
        )

        while self._keep_running:
            topic, payload = sub.receive()
            if topic == "playerstatus":
                with canvas(self.device) as draw:
                    draw.text((0, 0), payload["title"], fill="white")
                    if payload["repeat"] == "1":
                        draw.text((0, 10), "repeat", fill="white")
                    if payload["random"] == "1":
                        draw.text((0, 20), "random", fill="white")
                    if payload["single"] == "1":
                        draw.text((0, 30), "single", fill="white")
                    draw.text((0, 40), payload["song"], fill="white")
                    draw.text((0, 50), payload["state"], fill="white")

        logger.info("Exiting OLED Thread")

    def stop(self):
        """Stop the OLED thread."""
        logger.info("Stopping OLED Thread")

        self._keep_running = False
        # self.listen_done.clear()
        # self.action_done.set()


oled: OLED


@plugs.initialize
def initialize():
    """Setup connection and trigger the OLED loop."""
    global oled
    logger.info("Executing initialize handler, starting OLED process.")
    oled = OLED()
    oled.start()


@plugs.atexit
def atexit(signal_id: int, **ignored_kwargs):
    global oled
    logger.info("Executing atexit handler, stopping OLED process.")
    oled.stop()
