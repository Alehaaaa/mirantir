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

C_HEAD, C_QR, C_URL, C_CODE, C_BAR, C_COUNT, C_STATUS, C_CANCEL = \
    100, 101, 102, 103, 104, 105, 106, 500


def _tr(addon, string_id, *values):
    text = addon.getLocalizedString(string_id)
    return text.format(*values) if values else text


def _qr_png(data, path):
    try:
        url = ("https://api.qrserver.com/v1/create-qr-code/?size=360x360&margin=10&data="
               + urllib.parse.quote(data, safe=""))
        req = urllib.request.Request(url, headers={"User-Agent": "mirantir"})
        with urllib.request.urlopen(req, timeout=12) as r:
            png = r.read()
        if png[:4] == b"\x89PNG":
            with open(path, "wb") as f:
                f.write(png)
            return True
    except Exception:
        pass
    return False


class AuthDialog(xbmcgui.WindowXMLDialog):
    # attributes set by the caller before doModal(): .flow, .addon
    def onInit(self):
        self.result = None
        self._stop = False
        self._qr_file = os.path.join(tempfile.gettempdir(), "mirantir_qr.png")
        self._set(C_HEAD, _tr(self.addon, 32073, self.flow.name))
        self._refresh_display()
        threading.Thread(target=self._worker).start()

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

    def _set_qr(self):
        if _qr_png(self.flow.verify_url, self._qr_file):
            try:
                self.getControl(C_QR).setImage(self._qr_file, False)
            except Exception:
                pass

    def _refresh_display(self):
        self._set(C_URL, _tr(self.addon, 32074, self.flow.verify_url))
        self._set(C_CODE, str(self.flow.code))
        self._set(C_STATUS, _tr(self.addon, 32075))
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
                self._set_percent(100.0 * left / total)
                self._set(C_COUNT, _tr(self.addon, 32076, left))
                if time.time() - last_poll >= interval:
                    last_poll = time.time()
                    try:
                        st = self.flow.poll()
                    except Exception:
                        st = "pending"
                    if st == "ok":
                        self.result = getattr(self.flow, "result", None)
                        self._save()
                        self._set(C_STATUS, _tr(self.addon, 32077))
                        xbmc.sleep(700)
                        self._stop = True
                        self.close()
                        return
                    if st == "error":
                        break
                xbmc.sleep(500)
            if self._stop:
                break
            self._set(C_STATUS, _tr(self.addon, 32078))
            try:
                if not self.flow.start():
                    self._set(C_STATUS, _tr(self.addon, 32079))
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
