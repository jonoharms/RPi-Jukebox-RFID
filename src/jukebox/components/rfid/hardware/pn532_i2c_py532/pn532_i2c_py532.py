import logging

import ndef

from py532lib.mifare import Mifare
from py532lib.mifare import (MIFARE_WAIT_FOR_ENTRY, MIFARE_SAFE_RETRIES)  # noqa: F401

from components.rfid import ReaderBaseClass
import jukebox.cfghandler


from .description import DESCRIPTION


cfg = jukebox.cfghandler.get_handler('rfid')


def query_customization() -> dict:
    print("There are no customization parameters necessary!")
    return {'log_all_cards': False}


class ReaderClass(ReaderBaseClass):
    def __init__(self, reader_cfg_key):
        self._logger = logging.getLogger(f'jb.rfid.532({reader_cfg_key})')
        super().__init__(reader_cfg_key=reader_cfg_key, description=DESCRIPTION, logger=self._logger)

        self.log_all_cards = cfg.setndefault('rfid', 'readers', reader_cfg_key, 'config', 'log_all_cards', value=False)

        self.device = Mifare()
        self.device.SAMconfigure()
        # This would block scan_field() indefinitely
        # self.device.set_max_retries(MIFARE_WAIT_FOR_ENTRY)
        # This comes back every 5 tries, allowing a clean exit of this thread
        # And actually reduces CPU load by 0.3 %-points on a PI 3
        self.device.set_max_retries(MIFARE_SAFE_RETRIES)
        self._keep_running = True

    def cleanup(self):
        self.device.PN532.close()
        del self.device

    def stop(self):
        self._keep_running = False

    def read_card(self) -> dict:
        # scan_field returns a byte array -> convert to true integer
        # if no card is present comes back with False
        byte_uid = self.device.scan_field()
        if byte_uid is False:
            return {}
        if not self._keep_running:
            return {}
        try:
            card_uid = str(int(byte_uid.hex(), base=16))
        except ValueError:
            self._logger.debug(f"Error while reading card. Raw card ID = {byte_uid}")
            return {}

        if self.log_all_cards is True:
            self._logger.debug(f"Card detected with ID = {card_uid}")

        # Try to read NDEF data
        card_data = None
        try:
            # We try to read several blocks. For NTAG/Ultralight, data starts at page 4.
            # mifare_read(page) reads 16 bytes.
            # Page 4 contains NDEF TLV start (usually)
            raw_bytes = b''
            # Read first 64 bytes of user data (pages 4 to 19)
            for page in range(4, 20, 4):
                chunk = self.device.mifare_read(page)
                if chunk:
                    raw_bytes += chunk
                else:
                    break

            if raw_bytes:
                # Look for NDEF Message TLV (0x03)
                ndef_start = raw_bytes.find(b'\x03')
                if ndef_start != -1:
                    ndef_len = raw_bytes[ndef_start + 1]
                    # Handle 3-byte length field (0xFF followed by 2 bytes)
                    if ndef_len == 0xFF:
                        ndef_len = (raw_bytes[ndef_start + 2] << 8) + raw_bytes[ndef_start + 3]
                        ndef_payload = raw_bytes[ndef_start + 4: ndef_start + 4 + ndef_len]
                    else:
                        ndef_payload = raw_bytes[ndef_start + 2: ndef_start + 2 + ndef_len]

                    if ndef_payload:
                        decoder = ndef.message_decoder(ndef_payload)
                        for record in decoder:
                            if isinstance(record, ndef.uri.UriRecord):
                                card_data = record.uri
                                break
        except Exception as e:
            self._logger.debug(f"Error reading card data for {card_uid}: {e}")

        return {'id': card_uid, 'data': card_data}
