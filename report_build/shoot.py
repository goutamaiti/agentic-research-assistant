"""Capture light-theme screenshots of the running app (dev tool for the report)."""
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = "http://127.0.0.1:8011/#/"
DOC = "200d71db05324c31a20abc8e8a19e419"
OUT = r"L:\NLP_RB\report_build"
PORT = 9333

SHOTS = [
    ("shot_upload", "", 1280, 700),
    ("shot_analysis", f"analysis/{DOC}", 1280, 1500),
    ("shot_evidence", f"evidence/{DOC}", 1280, 1500),
    ("shot_assistant", f"assistant/{DOC}", 1280, 1000),
]

profile = tempfile.mkdtemp(prefix="chrome_shoot_")
proc = subprocess.Popen(
    [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
     f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    for _ in range(40):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")
            target = json.load(urllib.request.urlopen(req, timeout=2))
            break
        except Exception:
            time.sleep(0.5)
    else:
        sys.exit("chrome did not start")
    ws = connect(target["webSocketDebuggerUrl"], max_size=None)
    counter = [0]

    def call(method, **params):
        counter[0] += 1
        ws.send(json.dumps({"id": counter[0], "method": method, "params": params}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == counter[0]:
                return msg.get("result", msg)

    call("Page.enable")
    for name, route, w, h in SHOTS:
        call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1.5, mobile=False)
        call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
        call("Page.navigate", url=BASE + route)
        time.sleep(1.0)
        call("Page.navigate", url=BASE + route)  # hash change only; force a clean load
        call("Page.reload", ignoreCache=True)
        time.sleep(5)
        shot = call("Page.captureScreenshot", format="png", captureBeyondViewport=False)
        with open(f"{OUT}\\{name}.png", "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        print("saved", name)
        if name == "shot_evidence":
            call("Runtime.evaluate", expression="[...document.querySelectorAll('button')].find(b => /Unsupported/.test(b.textContent)).click()")
            time.sleep(2)
            shot = call("Page.captureScreenshot", format="png", captureBeyondViewport=False)
            with open(f"{OUT}\shot_evidence_unsupported.png", "wb") as f:
                f.write(base64.b64decode(shot["data"]))
            print("saved shot_evidence_unsupported")
    ws.close()
finally:
    proc.terminate()
