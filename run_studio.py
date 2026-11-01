import os
import sys
import time
import webbrowser
import threading

# Reconfigure stdout for utf-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
if STUDIO_DIR not in sys.path:
    sys.path.insert(0, STUDIO_DIR)

from web_studio.server import app

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://localhost:5050")

if __name__ == "__main__":
    print("=" * 60)
    print("       >>> LOCKET CUSTOM STUDIO DANG KHOI CHAY... <<<")
    print("       - Video sieu dai 2 - 5 Phut (Apple HEVC <6MB)")
    print("       - Khung anh doc quyen: Retro 35mm, Polaroid, Cyberpunk")
    print("       - Card Thoi tiet & Live Radar kinh mo (Open-Meteo)")
    print("=" * 60)
    print("Truy cap tai: http://localhost:5050")
    print("Dang tu dong mo trinh duyet...")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=5050, debug=False)
