# -*- coding: utf-8 -*-
"""Debrid: AllDebrid + RealDebrid, configurable at once and used as mutual
fallbacks. Includes the QR/device auth flows and RealDebrid token refresh.

Settings used:
  ad_token          AllDebrid API key
  rd_token          RealDebrid access token (API token or OAuth access token)
  rd_refresh        RealDebrid OAuth refresh code (device flow)
  rd_client_id      RealDebrid OAuth client id   (device flow)
  rd_client_secret  RealDebrid OAuth client secret (device flow)
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "mirantir"
RD_CLIENT_ID = "X245A4XAIBGVM"   # public open-source RealDebrid client id
RD_API = "https://api.real-debrid.com"
AD_API = "https://api.alldebrid.com/v4"


# --------------------------------------------------------------------------- #
# low-level HTTP
# --------------------------------------------------------------------------- #
def _get_json(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _post_json(url, data, headers=None, timeout=30):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# --------------------------------------------------------------------------- #
# unlock
# --------------------------------------------------------------------------- #
def _ad_unlock(key, link):
    q = urllib.parse.urlencode({"agent": UA, "apikey": key, "link": link})
    try:
        j = _get_json(AD_API + "/link/unlock?" + q)
    except Exception as e:
        return None, str(e)
    if j.get("status") == "success":
        return (j.get("data", {}) or {}).get("link"), None
    return None, (j.get("error", {}) or {}).get("code", "ad_error")


def _rd_unlock(token, link):
    try:
        j = _post_json(RD_API + "/rest/1.0/unrestrict/link", {"link": link},
                       headers={"Authorization": "Bearer " + token, "User-Agent": UA})
    except urllib.error.HTTPError as e:
        try:
            return None, json.load(e).get("error", "HTTP %s" % e.code), e.code
        except Exception:
            return None, "HTTP %s" % e.code, e.code
    except Exception as e:
        return None, str(e), 0
    return j.get("download"), None, 200


def configured(addon):
    """Return list of (provider, token) for every configured service, in order."""
    provs = []
    ad = (addon.getSetting("ad_token") or "").strip()
    rd = (addon.getSetting("rd_token") or "").strip()
    if ad:
        provs.append(("ad", ad))
    if rd:
        provs.append(("rd", rd))
    return provs


def unlock_any(addon, link, used=None):
    """Try each configured provider until one unlocks `link`.
    Returns (direct_url, error, provider)."""
    errs = []
    for prov, token in configured(addon):
        if used is not None and prov in used:
            continue
        if prov == "ad":
            direct, err = _ad_unlock(token, link)
        else:
            direct, err, code = _rd_unlock(token, link)
            if not direct and (code == 401 or err in ("bad_token", "expired")):
                new = rd_refresh(addon)
                if new:
                    direct, err, code = _rd_unlock(new, link)
        if direct:
            return direct, None, prov
        errs.append("%s:%s" % (prov, err))
    return None, "; ".join(errs) or "sin proveedor", None


# --------------------------------------------------------------------------- #
# RealDebrid token refresh (OAuth device creds)
# --------------------------------------------------------------------------- #
def rd_refresh(addon):
    rt = (addon.getSetting("rd_refresh") or "").strip()
    cid = (addon.getSetting("rd_client_id") or "").strip()
    cs = (addon.getSetting("rd_client_secret") or "").strip()
    if not (rt and cid and cs):
        return None
    try:
        j = _post_json(RD_API + "/oauth/v2/token", {
            "client_id": cid, "client_secret": cs, "code": rt,
            "grant_type": "http://oauth.net/grant_type/device/1.0"})
    except Exception:
        return None
    tok = j.get("access_token")
    if tok:
        addon.setSetting("rd_token", tok)
    return tok


# --------------------------------------------------------------------------- #
# Auth flows — each returns a small object the auth dialog drives.
# --------------------------------------------------------------------------- #
class AllDebridFlow(object):
    name = "AllDebrid"
    manual_url = "https://alldebrid.com/pin"

    def start(self):
        j = _get_json(AD_API + "/pin/get?agent=" + UA)
        d = j.get("data", {}) if j.get("status") == "success" else {}
        self.check_url = d.get("check_url")
        self.code = d.get("pin", "")
        self.verify_url = d.get("user_url") or self.manual_url
        self.expires_in = int(d.get("expires_in", 600))
        self.interval = 5
        return bool(self.check_url)

    def poll(self):
        """-> 'ok' | 'pending' | 'error'. On ok, self.result holds the apikey."""
        try:
            j = _get_json(self.check_url)
        except Exception:
            return "pending"
        if j.get("status") != "success":
            return "pending"
        d = j.get("data", {})
        if d.get("activated") and d.get("apikey"):
            self.result = {"ad_token": d["apikey"]}
            return "ok"
        if d.get("expired"):
            return "error"
        return "pending"


class RealDebridFlow(object):
    name = "RealDebrid"
    manual_url = "https://real-debrid.com/device"

    def start(self):
        j = _get_json(RD_API + "/oauth/v2/device/code?client_id=%s&new_credentials=yes"
                      % RD_CLIENT_ID)
        self.device_code = j.get("device_code")
        self.code = j.get("user_code", "")
        self.verify_url = (j.get("direct_verification_url") or
                           j.get("verification_url") or self.manual_url)
        self.expires_in = int(j.get("expires_in", 600))
        self.interval = int(j.get("interval", 5))
        self._cid = self._cs = None
        return bool(self.device_code)

    def poll(self):
        try:
            if not self._cid:
                j = _get_json(RD_API + "/oauth/v2/device/credentials?client_id=%s&code=%s"
                              % (RD_CLIENT_ID, self.device_code))
                if not j.get("client_id"):
                    return "pending"
                self._cid, self._cs = j["client_id"], j["client_secret"]
            tok = _post_json(RD_API + "/oauth/v2/token", {
                "client_id": self._cid, "client_secret": self._cs,
                "code": self.device_code,
                "grant_type": "http://oauth.net/grant_type/device/1.0"})
            if tok.get("access_token"):
                self.result = {
                    "rd_token": tok["access_token"],
                    "rd_refresh": tok.get("refresh_token", ""),
                    "rd_client_id": self._cid, "rd_client_secret": self._cs,
                }
                return "ok"
        except urllib.error.HTTPError:
            return "pending"
        except Exception:
            return "pending"
        return "pending"


def make_flow(service):
    return AllDebridFlow() if service == "ad" else RealDebridFlow()
