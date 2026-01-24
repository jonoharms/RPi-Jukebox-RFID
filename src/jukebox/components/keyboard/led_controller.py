# /// script
# dependencies = [
#   "hid==1.0.8",
# ]
# ///

import hid
import time
import sys

VID = 0xCAFE
PID = 0xBABE
USAGE_PAGE = 0xFF00

class LedController:
    def __init__(self):
        self.device = None
        self.path = self._find_device_path()
        
        if not self.path:
            raise Exception(f"Could not find Raw HID device {hex(VID)}:{hex(PID)} with Usage Page {hex(USAGE_PAGE)}")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _find_device_path(self):
        # hid.enumerate() might return a list of dicts or DeviceInfo objects
        for info in hid.enumerate(VID, PID):
            # Try to get usage_page regardless of type
            usage_page = 0
            path = None
            
            if isinstance(info, dict):
                usage_page = info.get('usage_page', 0)
                path = info.get('path')
            else:
                usage_page = getattr(info, 'usage_page', 0)
                path = getattr(info, 'path', None)

            if usage_page == USAGE_PAGE and path:
                return path
        return None

    def open(self):
        if not self.device:
            # In hid 1.0.8, we use hid.Device(path=...)
            self.device = hid.Device(path=self.path)

    def close(self):
        if self.device:
            self.device.close()
            self.device = None

    def set_color(self, index, r, g, b):
        self.open()
        
        # Packet Format: [Report ID, Command, Index, R, G, B, ...padding...]
        report_id = 0x01
        command = 0x01
        
        # Construct 64-byte payload. 
        # hid.Device.write() takes bytes or a list of integers.
        data = [command, index, r, g, b] + [0] * 58
        
        try:
            # hid.Device.write() in 1.0.8 usually expects the Report ID as the first argument 
            # if the underlying hid_write is used, or it might be part of the buffer.
            # Most hidapi wrappers expect [ReportID, Data...].
            self.device.write(bytes([report_id] + data))
            time.sleep(0.01)
        except Exception as e:
            print(f"Error writing to device: {e}")
            self.close() 

    def chase_animation(self, loops=3):
        print("Starting LED Chase...")
        led_count = 6
        
        colors = [
            (255, 0, 0),   # Red
            (0, 255, 0),   # Green
            (0, 0, 255),   # Blue
        ]

        try:
            for _ in range(loops):
                for r, g, b in colors:
                    for i in range(led_count):
                        self.set_color(i, r, g, b)
                        time.sleep(0.05)
                        self.set_color(i, 0, 0, 0)
                        time.sleep(0.01) 
            for _ in range(loops):
                print("Flash White")
                for i in range(led_count):
                    self.set_color(i, 50, 50, 50)
                    time.sleep(0.01)
                time.sleep(0.1)
                for i in range(led_count):
                    self.set_color(i, 0, 0, 0)
                    time.sleep(0.01)
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

if __name__ == "__main__":
    try:
        controller = LedController()
        controller.chase_animation()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)