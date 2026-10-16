"""
Safely find and terminate any process listening on ports 8000 or 5173.
Used by start.bat and stop.bat to prevent port collision and zombie processes.
"""
import sys

def free_ports(ports=(8000, 5173)):
    try:
        import psutil
    except ImportError:
        return

    terminated = 0
    for p in psutil.process_iter(['pid', 'name']):
        try:
            for c in p.net_connections(kind='tcp'):
                if c.laddr and c.laddr.port in ports and c.status == 'LISTEN':
                    try:
                        p.terminate()
                        p.wait(timeout=1.5)
                    except (psutil.TimeoutExpired, psutil.AccessDenied):
                        p.kill()
                    terminated += 1
        except (psutil.AccessDenied, psutil.NoSuchProcess, Exception):
            pass

    if terminated > 0:
        print(f"[Cleanup] Terminated {terminated} process(es) holding ports {ports}")

if __name__ == "__main__":
    free_ports()
