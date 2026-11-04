# -*- coding: utf-8 -*-
"""QR / device-code auth dialog for AllDebrid & RealDebrid (Mirantir).

A WindowXMLDialog (skin: resources/skins/Default/1080i/mirantir_auth.xml) that
shows the pairing code, a QR for the verification URL, a countdown progress bar
that auto-refreshes the code when it expires, and a Cancel button (or Back).
"""

import os
import threading
import time
import tempfile
import urllib.parse
import urllib.request

import xbmc
import xbmcgui

_ACTION_CANCEL = (9, 10, 92)   # parent dir / previous menu / nav back

C_HEAD, C_QR, C_BAR, C_TEXT, C_CANCEL = 100, 101, 104, 107, 500

_ENGLISH_FALLBACK = {
    32069: "Error: {0}",
    32073: "Connect {0}",
    32074: "Visit: {0}",
    32075: "Waiting for confirmation...",
    32076: "New code in {0}s",
    32077: "Connected!",
    32078: "Generating a new code...",
    32079: "Could not generate a code",
    32080: "Could not start the connection",
    32081: "Could not open the dialog: {0}",
}


def _tr(addon, string_id, *values):
    text = addon.getLocalizedString(string_id) or _ENGLISH_FALLBACK.get(string_id, "")
    return text.format(*values) if values else text


def _qr_png(data, path):
    try:
        url = ("https://api.qrserver.com/v1/create-qr-code/"
               "?size=360x360&margin=10&data=" + urllib.parse.quote(data, safe=""))
        req = urllib.request.Request(url, headers={"User-Agent": "mirantir"})
        with urllib.request.urlopen(req, timeout=12) as response:
            png = response.read()
        if png[:4] == b"\x89PNG":
            with open(path, "wb") as output:
                output.write(png)
            return True
    except Exception:
        pass
    return False


class AuthDialog(xbmcgui.WindowXMLDialog):
    # attributes set by the caller before doModal(): .flow, .addon
    def onInit(self):
        self.result = None
        self._stop = False
        self._seconds_left = int(getattr(self.flow, "expires_in", 600))
        self._status = _tr(self.addon, 32075)
        self._qr_file = os.path.join(tempfile.gettempdir(), "mirantir_qr.png")
        self._set(C_HEAD, _tr(self.addon, 32073, self.flow.name))
        self._set(C_CANCEL, xbmc.getLocalizedString(222) or "Cancel")
        self._refresh_display()
        threading.Thread(target=self._worker, name="MirantirAuth", daemon=True).start()

    # ---- helpers --------------------------------------------------------- #
    def _set(self, cid, text):
        try:
            self.getControl(cid).setLabel(text)
        except Exception:
            pass

    def _set_percent(self, pct):
        try:
            self.getControl(C_BAR).setPercent(max(0.0, min(100.0, float(pct))))
        except Exception:
            pass

    def _set_text(self):
        text = "[CR]".join((
            _tr(self.addon, 32074, self.flow.verify_url),
            "",
            str(self.flow.code),
            "",
            _tr(self.addon, 32076, self._seconds_left),
            self._status,
        ))
        try:
            self.getControl(C_TEXT).setText(text)
        except Exception:
            pass

    def _set_qr(self):
        if _qr_png(self.flow.verify_url, self._qr_file):
            try:
                self.getControl(C_QR).setImage(self._qr_file, False)
            except Exception:
                pass

    def _refresh_display(self):
        self._status = _tr(self.addon, 32075)
        self._set_text()
        self._set_qr()

    # ---- worker ---------------------------------------------------------- #
    def _worker(self):
        while not self._stop:
            total = max(30, int(getattr(self.flow, "expires_in", 600)))
            interval = max(2, int(getattr(self.flow, "interval", 4)))
            deadline = time.time() + total
            last_poll = 0.0
            while not self._stop and time.time() < deadline:
                left = int(deadline - time.time())
                self._seconds_left = left
                self._set_percent(100.0 * left / total)
                self._set_text()
                if time.time() - last_poll >= interval:
                    last_poll = time.time()
                    try:
                        st = self.flow.poll()
                    except Exception:
                        st = "pending"
                    if st == "ok":
                        self.result = getattr(self.flow, "result", None)
                        self._save()
                        self._status = _tr(self.addon, 32077)
                        self._set_text()
                        xbmc.sleep(700)
                        self._stop = True
                        self.close()
                        return
                    if st == "error":
                        break
                xbmc.sleep(500)
            if self._stop:
                break
            self._status = _tr(self.addon, 32078)
            self._set_text()
            try:
                if not self.flow.start():
                    self._status = _tr(self.addon, 32079)
                    self._set_text()
                    xbmc.sleep(2500)
                    break
                self._refresh_display()
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
    def onClick(self, cid):
        if cid == C_CANCEL:
            self._stop = True
            self.close()

    def onAction(self, action):
        if action.getId() in _ACTION_CANCEL:
            self._stop = True
            self.close()


def run_auth(flow, addon, addon_path):
    """Start a flow and show the dialog. Returns True if tokens were saved."""
    try:
        if not flow.start():
            xbmcgui.Dialog().notification("Mirantir", _tr(addon, 32080),
                                          xbmcgui.NOTIFICATION_ERROR)
            return False
    except Exception as e:
        xbmcgui.Dialog().notification("Mirantir", _tr(addon, 32069, e),
                                      xbmcgui.NOTIFICATION_ERROR)
        return False
    try:
        dlg = AuthDialog("mirantir_auth.xml", addon_path, "Default", "1080i")
    except Exception as e:
        xbmcgui.Dialog().notification("Mirantir", _tr(addon, 32081, e),
                                      xbmcgui.NOTIFICATION_ERROR)
        return False
    dlg.flow = flow
    dlg.addon = addon
    dlg.doModal()
    ok = bool(getattr(dlg, "result", None))
    del dlg
    return ok
