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
        # We use the underlying PN532 object to get more info (like SAK)
        # scan_field in Mifare class is a bit limited.
        # However, to keep compatibility with the existing setup, we first try to get UID.
        
        try:
            # MIFARE_SAFE_RETRIES is used here
            byte_uid = self.device.scan_field()
        except Exception as e:
            self._logger.debug(f"Scan field error: {e}")
            return {}

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
            # Give the tag a moment to breathe
            # time.sleep(0.01)
            
            # Check card type if possible. 
            # Standard Mifare Classic has 4 byte UID. 
            # NTAG/Ultralight has 7 byte UID.
            is_classic = (len(byte_uid) == 4)
            
            if is_classic:
                # Mifare Classic needs authentication.
                # Try factory default key first, then NDEF key.
                # Sector 0, Block 1 is a good place to look for NDEF TLV if it's there.
                # But usually NDEF starts in Sector 1 for Classic.
                keys = [b'\xff\xff\xff\xff\xff\xff', b'\xd3\xf7\xd3\xf7\xd3\xf7']
                authenticated = False
                for key in keys:
                    try:
                        # Authenticate Sector 1 (Block 4) for NDEF
                        self.device.mifare_auth_a(self.device.mifare_address(1, 0), key)
                        authenticated = True
                        break
                    except Exception:
                        continue
                
                if authenticated:
                    # Read Sector 1, Blocks 4, 5, 6
                    raw_bytes = self.device.mifare_read(self.device.mifare_address(1, 0))
                    raw_bytes += self.device.mifare_read(self.device.mifare_address(1, 1))
                else:
                    raw_bytes = b''
            else:
                # NTAG / Ultralight (e.g. NTAG215)
                raw_bytes = b''
                # Read up to 496 bytes of user data (pages 4 to 127)
                # mifare_read(page) reads 16 bytes (4 pages) at a time
                for page in range(4, 128, 4):
                    try:
                        chunk = self.device.mifare_read(page)
                        if chunk:
                            raw_bytes += chunk
                        else:
                            break
                        
                        # Optimization: Check if we have the full NDEF message yet
                        # to avoid unnecessary reads and potential timeouts
                        if len(raw_bytes) > 2:
                            ndef_start = raw_bytes.find(b'\x03')
                            if ndef_start != -1 and len(raw_bytes) > ndef_start + 1:
                                ndef_len = raw_bytes[ndef_start + 1]
                                if ndef_len != 0xFF:
                                    # 1-byte length field
                                    if len(raw_bytes) >= ndef_start + 2 + ndef_len:
                                        break
                                elif len(raw_bytes) > ndef_start + 3:
                                    # 3-byte length field (0xFF followed by 2 bytes)
                                    full_len = (raw_bytes[ndef_start + 2] << 8) + raw_bytes[ndef_start + 3]
                                    if len(raw_bytes) >= ndef_start + 4 + full_len:
                                        break
                    except Exception as e:
                        if "0x1" in str(e):
                            self._logger.debug(f"Timeout reading page {page}, card might have moved.")
                        else:
                            self._logger.debug(f"Error reading page {page}: {e}")
                        break

            if raw_bytes:
                # Look for NDEF Message TLV (0x03)
                ndef_start = raw_bytes.find(b'\x03')
                if ndef_start != -1 and len(raw_bytes) > ndef_start + 1:
                    ndef_len = raw_bytes[ndef_start + 1]
                    # Handle 3-byte length field (0xFF followed by 2 bytes)
                    payload_start = ndef_start + 2
                    if ndef_len == 0xFF and len(raw_bytes) > ndef_start + 3:
                        ndef_len = (raw_bytes[ndef_start + 2] << 8) + raw_bytes[ndef_start + 3]
                        payload_start = ndef_start + 4
                    
                    if len(raw_bytes) >= payload_start + ndef_len:
                        ndef_payload = raw_bytes[payload_start : payload_start + ndef_len]
                        decoder = ndef.message_decoder(ndef_payload)
                        for record in decoder:
                            if isinstance(record, ndef.uri.UriRecord):
                                card_data = record.uri
                                break
        except Exception as e:
            # We don't want to crash the whole reader thread just because data read failed
            # If we have the UID, that's already something.
            self._logger.debug(f"Data read skipped for {card_uid}: {e}")

        return {'id': card_uid, 'data': card_data}
