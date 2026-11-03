# -*- coding: utf-8 -*-
"""QR / device-code auth dialog for AllDebrid & RealDebrid.

A programmatic WindowDialog (no skin XML needed, so it works under any skin):
shows the pairing code, a QR for the verification URL, a countdown bar, and
auto-refreshes the code when it expires. Press Back to cancel.
"""

import os
import time
import tempfile
import urllib.parse
import urllib.request

import xbmc
import xbmcgui
import xbmcvfs

_ACTION_CANCEL = (9, 10, 92, 247)   # back / previous-menu / nav-back


def _qr_png(data, path):
    """Fetch a QR PNG for `data`. Returns True on success."""
    try:
        url = ("https://api.qrserver.com/v1/create-qr-code/?size=420x420&margin=12&data="
               + urllib.parse.quote(data, safe=""))
        req = urllib.request.Request(url, headers={"User-Agent": "palantir"})
        with urllib.request.urlopen(req, timeout=12) as r:
            png = r.read()
        if png[:4] == b"\x89PNG":
            with open(path, "wb") as f:
                f.write(png)
            return True
    except Exception:
        pass
    return False


class AuthDialog(xbmcgui.WindowDialog):
    def __init__(self, flow, addon, bg_path):
        self.flow = flow
        self.addon = addon
        self.bg_path = bg_path
        self.result = None
        self.canceled = False
        self._stop = False
        self._qr_file = os.path.join(tempfile.gettempdir(), "palantir_qr.png")
        self._controls = {}

    # ---- layout ---------------------------------------------------------- #
    def onInit(self):
        W, H = self.getWidth(), self.getHeight()
        pw, ph = int(W * 0.6), int(H * 0.8)
        px, py = (W - pw) // 2, (H - ph) // 2
        cx = W // 2

        self.addControl(xbmcgui.ControlImage(0, 0, W, H, self.bg_path))
        self.addControl(xbmcgui.ControlImage(px, py, pw, ph, self.bg_path))

        self._add("head", xbmcgui.ControlLabel(
            px, py + 24, pw, 48, "Conectar %s" % self.flow.name,
            font="font30_title", textColor="FFFFFFFF", alignment=2))

        qr = 300
        self._add("qr", xbmcgui.ControlImage(cx - qr // 2, py + 90, qr, qr, ""))

        self._add("url", xbmcgui.ControlLabel(
            px, py + 90 + qr + 16, pw, 36,
            "Visita:  [B]%s[/B]" % self.flow.verify_url,
            textColor="FFDDDDDD", alignment=2))
        self._add("code", xbmcgui.ControlLabel(
            px, py + 90 + qr + 54, pw, 60,
            "Código:  [B][COLOR FFFFD400]%s[/COLOR][/B]" % self.flow.code,
            font="font30_title", textColor="FFFFFFFF", alignment=2))
        self._add("bar", xbmcgui.ControlLabel(
            px, py + ph - 100, pw, 36, "", textColor="FF66CCFF", alignment=2))
        self._add("status", xbmcgui.ControlLabel(
            px, py + ph - 60, pw, 36, "Esperando confirmación…  (Atrás para cancelar)",
            textColor="FFAAAAAA", alignment=2))

        self._set_qr(self.flow.verify_url + "  " + str(self.flow.code))
        import threading
        threading.Thread(target=self._worker).start()

    def _add(self, key, ctrl):
        self._controls[key] = ctrl
        self.addControl(ctrl)
        return ctrl

    # ---- display helpers ------------------------------------------------- #
    def _set_qr(self, data):
        if _qr_png(data, self._qr_file):
            try:
                self._controls["qr"].setImage(self._qr_file, False)
            except Exception:
                pass

    def _refresh_display(self):
        try:
            self._controls["url"].setLabel("Visita:  [B]%s[/B]" % self.flow.verify_url)
            self._controls["code"].setLabel(
                "Código:  [B][COLOR FFFFD400]%s[/COLOR][/B]" % self.flow.code)
        except Exception:
            pass
        self._set_qr(self.flow.verify_url + "  " + str(self.flow.code))

    def _set_status(self, txt):
        try:
            self._controls["status"].setLabel(txt)
        except Exception:
            pass

    def _set_bar(self, left, total):
        try:
            n = 24
            fill = max(0, min(n, int(n * left / max(1, total))))
            bar = "[" + "█" * fill + "░" * (n - fill) + "]  %ds" % left
            self._controls["bar"].setLabel(bar)
        except Exception:
            pass

    # ---- worker ---------------------------------------------------------- #
    def _worker(self):
        while not self._stop:
            total = max(30, int(getattr(self.flow, "expires_in", 600)))
            interval = max(2, int(getattr(self.flow, "interval", 4)))
            deadline = time.time() + total
            last_poll = 0.0
            while not self._stop and time.time() < deadline:
                left = int(deadline - time.time())
                self._set_bar(left, total)
                if time.time() - last_poll >= interval:
                    last_poll = time.time()
                    try:
                        st = self.flow.poll()
                    except Exception:
                        st = "pending"
                    if st == "ok":
                        self.result = getattr(self.flow, "result", None)
                        self._save()
                        self._set_status("¡Conectado!")
                        xbmc.sleep(600)
                        self._stop = True
                        self.close()
                        return
                    if st == "error":
                        break
                xbmc.sleep(500)
            if self._stop:
                break
            # expired -> new code automatically
            self._set_status("Código caducado — generando uno nuevo…")
            try:
                if not self.flow.start():
                    self._set_status("No se pudo generar el código")
                    xbmc.sleep(2500)
                    break
                self._refresh_display()
                self._set_status("Esperando confirmación…  (Atrás para cancelar)")
            except Exception:
                break
        self.close()

    def _save(self):
        if not self.result:
            return
        for k, v in self.result.items():
            try:
                self.addon.setSetting(k, v)
            except Exception:
                pass

    # ---- input ----------------------------------------------------------- #
    def onAction(self, action):
        if action.getId() in _ACTION_CANCEL:
            self.canceled = True
            self._stop = True
            self.close()


def run_auth(flow, addon, bg_path):
    """Start a flow and show the dialog. Returns True if tokens were saved."""
    try:
        if not flow.start():
            xbmcgui.Dialog().notification("Palantir Local",
                                          "No se pudo iniciar la conexión",
                                          xbmcgui.NOTIFICATION_ERROR)
            return False
    except Exception as e:
        xbmcgui.Dialog().notification("Palantir Local", "Error: %s" % e,
                                      xbmcgui.NOTIFICATION_ERROR)
        return False
    dlg = AuthDialog(flow, addon, bg_path)
    dlg.doModal()
    ok = bool(getattr(dlg, "result", None))
    del dlg
    return ok
