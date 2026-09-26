import time
from multiprocessing import Process, freeze_support
from multiprocessing.connection import Client
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from app import ui
    from app import stats_service
except ImportError:
    import ui
    import stats_service

def start_service(address=("localhost", 6000), authkey=b"corepulse"):
    stats_service.run_server(address=address, authkey=authkey)

def wait_for_service(address=("localhost", 6000), authkey=b"corepulse", timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            c = Client(address=address, authkey=authkey)
            c.close()
            return True
        except Exception:
            time.sleep(0.1)
    return False

def main():
    address = ("localhost", 6000)
    authkey = b"corepulse"
    p = Process(target=start_service, args=(address, authkey), daemon=True)
    p.start()
    wait_for_service(address=address, authkey=authkey, timeout=5.0)
    try:
        ui.run_app(address=address, authkey=authkey)
    finally:
        try:
            c = Client(address=address, authkey=authkey)
            c.send("quit")
            c.close()
        except Exception:
            pass
        try:
            p.join(timeout=1.0)
        except Exception:
            pass

if __name__ == "__main__":
    freeze_support()
    main()
