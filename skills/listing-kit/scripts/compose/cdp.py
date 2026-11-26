#!/usr/bin/env python3
"""Drive a headless Chromium-family browser over --remote-debugging-pipe.

Standard library only. The browser never loads anything from disk or the network:
every request is answered here from an allow-list (see Renderer.render), anything
else is refused. Protocol: JSON messages terminated by a NUL byte; the browser
reads commands on file descriptor 3 and writes replies and events on 4.
"""
import base64
import json
import os
import select
import shutil
import subprocess
import tempfile

ORIGIN = "https://compose.listing-kit.invalid"

CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "brave-browser",
]

MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".json": "application/json",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml", ".ttf": "font/ttf", ".otf": "font/otf"}


class BrowserError(Exception):
    pass


def find_browser():
    env = os.environ.get("LK_BROWSER")
    for cand in ([env] if env else []) + CANDIDATES:
        path = cand if os.path.isabs(cand) else shutil.which(cand)
        if path and os.access(path, os.X_OK):
            return path
    return None


class Browser:
    def __init__(self, path=None, extra_args=None):
        self.path = path or find_browser()
        if not self.path:
            raise BrowserError("Framed screenshots need Chrome, Chromium, Edge or Brave. Found none.")
        self.profile = tempfile.mkdtemp(prefix="lk-browser-")
        to_browser_r, self._w = os.pipe()
        self._r, from_browser_w = os.pipe()

        def wire():  # the browser expects exactly fds 3 (in) and 4 (out)
            a, b = os.dup(to_browser_r), os.dup(from_browser_w)
            os.dup2(a, 3); os.dup2(b, 4)
            for fd in (a, b):
                if fd not in (3, 4):
                    os.close(fd)

        args = [self.path, "--headless=new", "--remote-debugging-pipe",
                "--user-data-dir=" + self.profile, "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-background-networking", "--disable-sync",
                "--disable-component-update", "--hide-scrollbars",
                # No keychain or password store: with an unusual HOME (CI, sandboxes) the real
                # ones can block the browser's start forever.
                "--use-mock-keychain", "--password-store=basic", "--disable-features=DialMediaRouteProvider", "--force-color-profile=srgb",
                "--font-render-hinting=none",
                # Second barrier: nothing reaches a network, loopback included.
                "--proxy-server=socks5://127.0.0.1:1", "--proxy-bypass-list=<-loopback>",
                "about:blank"]
        args[1:1] = (extra_args or []) + os.environ.get("LK_BROWSER_ARGS", "").split()
        self.proc = subprocess.Popen(args, preexec_fn=wire, pass_fds=(3, 4), close_fds=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        os.close(to_browser_r); os.close(from_browser_w)
        self._buf = b""
        self.timeout = int(os.environ.get("LK_BROWSER_TIMEOUT", "30"))
        self._id = 0
        self.events = []

    def version_major(self):
        """The browser's major version, for the compose lock's renderer fingerprint."""
        try:
            product = self.call("Browser.getVersion").get("product", "")
            return product.split("/", 1)[1].split(".", 1)[0]
        except (BrowserError, IndexError):
            return "unknown"

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        for fd in (self._r, self._w):
            try:
                os.close(fd)
            except OSError:
                pass
        shutil.rmtree(self.profile, ignore_errors=True)

    def _read(self):
        while b"\0" not in self._buf:
            # A browser that never answers must not hang the caller forever.
            ready, _, _ = select.select([self._r], [], [], self.timeout)
            if not ready:
                raise BrowserError("the browser did not answer within %d seconds (%s)" % (self.timeout, self.path))
            chunk = os.read(self._r, 1 << 20)
            if not chunk:
                raise BrowserError("the browser closed the connection (exit %s)" % self.proc.poll())
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\0", 1)
        return json.loads(raw)

    def send(self, method, params=None, session=None):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        os.write(self._w, json.dumps(msg).encode() + b"\0")
        return self._id

    def call(self, method, params=None, session=None, on_event=None):
        """Send a command and return its result, handing events to on_event meanwhile."""
        want = self.send(method, params, session)
        while True:
            msg = self._read()
            if msg.get("id") == want:
                if "error" in msg:
                    raise BrowserError("%s: %s" % (method, msg["error"].get("message")))
                return msg.get("result", {})
            if "method" in msg and on_event:
                on_event(msg)

    def pump(self, on_event, until):
        while not until():
            msg = self._read()
            if "method" in msg:
                on_event(msg)


class Renderer:
    """Render pages whose every request is served from `assets` (url path -> file path or bytes)."""

    def __init__(self, browser):
        self.b = browser
        self.refused = []

    def render(self, assets, width, height, page="/index.html", probe=None, csp=True):
        """csp=False drops the Content-Security-Policy header so tests can prove the request
        interception refuses everything off the allow-list by itself."""
        b = self.b
        self.refused = []
        target = b.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        session = b.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        state = {"loaded": False}

        def serve(msg):
            m, p, sid = msg["method"], msg.get("params", {}), msg.get("sessionId")
            if m == "Target.attachedToTarget":  # workers and frames: intercept there too
                child = p["sessionId"]
                b.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]}, child)
                b.send("Runtime.runIfWaitingForDebugger", {}, child)
            elif m == "Fetch.requestPaused":
                url = p["request"]["url"]
                body = None
                if url.startswith(ORIGIN + "/"):
                    path = "/" + url[len(ORIGIN) + 1:].split("?", 1)[0].split("#", 1)[0]
                    src = assets.get(path)
                    if isinstance(src, (bytes, bytearray)):
                        body = bytes(src)
                    elif src:
                        with open(src, "rb") as f:
                            body = f.read()
                if body is None:
                    self.refused.append(url)
                    b.send("Fetch.failRequest", {"requestId": p["requestId"], "errorReason": "AccessDenied"}, sid)
                else:
                    ext = os.path.splitext(url.split("?", 1)[0])[1].lower()
                    b.send("Fetch.fulfillRequest", {
                        "requestId": p["requestId"], "responseCode": 200,
                        "responseHeaders": [
                            {"name": "Content-Type", "value": MIME.get(ext, "application/octet-stream")}
                        ] + ([{"name": "Content-Security-Policy",
                               "value": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"}]
                             if csp else []),
                        "body": base64.b64encode(body).decode()}, sid)
            elif m == "Page.loadEventFired" and sid == session:
                state["loaded"] = True

        b.call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]}, session, serve)
        b.call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True},
               session, serve)
        b.call("Page.enable", {}, session, serve)
        b.call("Emulation.setDeviceMetricsOverride",
               {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False}, session, serve)
        b.call("Page.navigate", {"url": ORIGIN + page}, session, serve)
        b.pump(serve, lambda: state["loaded"])
        ready = ("(async()=>{await document.fonts.ready;"
                 "await Promise.all([...document.images].map(i=>i.decode().catch(()=>0)));"
                 "return JSON.stringify(%s)})()" % (probe or "null"))
        res = b.call("Runtime.evaluate", {"expression": ready, "awaitPromise": True, "returnByValue": True},
                     session, serve)
        if "exceptionDetails" in res:
            raise BrowserError("template script failed: %s" % res["exceptionDetails"].get("text"))
        info = json.loads(res["result"].get("value") or "null")
        shot = b.call("Page.captureScreenshot",
                      {"format": "png", "captureBeyondViewport": False,
                       "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1}},
                      session, serve)
        b.call("Target.closeTarget", {"targetId": target}, None, serve)
        return base64.b64decode(shot["data"]), info
