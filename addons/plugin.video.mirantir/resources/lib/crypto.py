# -*- coding: utf-8 -*-
"""
crypto.py — decrypt Mirantir stream links (pure-Python, no deps).

Each enlaces_*.link value is AES-256-OFB encrypted (with a hardcoded key found
in the addon's libs/ioI1I1ii1 module) of a https://1fichier.com/?... URL:

    blob = b64decode("hTh8uRnL5bX8PZC6Tc3t46nVDFfBpB6Tjw3qazQThpexpg8bLdimevNHj5vJR0nP")
    key, iv = blob[16:], blob[:16]          # 32-byte key, 16-byte IV
    url = AES(key, OFB, iv).decrypt(urlsafe_b64decode(link))

Only AES block *encryption* is needed (OFB builds its keystream from E(IV),
E(E(IV)), ...), so this file implements just that. Validated against a known
vector in the __main__ self-test.
"""

import base64

# --- AES tables ------------------------------------------------------------ #
_SBOX = []
def _init_sbox():
    p = q = 1
    sbox = [0] * 256
    while True:
        # multiply p by 3 in GF(2^8)
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        # divide q by 3
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        q ^= 0x09 if q & 0x80 else 0
        q &= 0xFF
        xformed = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) \
            ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        sbox[p] = (xformed ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox

_SBOX = _init_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
         0x6C, 0xD8, 0xAB, 0x4D]


def _xtime(a):
    a <<= 1
    if a & 0x100:
        a ^= 0x11B
    return a & 0xFF


def _mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        b >>= 1
        a = _xtime(a)
    return r & 0xFF


class AES:
    def __init__(self, key):
        assert len(key) in (16, 24, 32)
        self.nk = len(key) // 4
        self.nr = {4: 10, 6: 12, 8: 14}[self.nk]
        self.rk = self._expand(key)

    def _expand(self, key):
        nk, nr = self.nk, self.nr
        w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
        for i in range(nk, 4 * (nr + 1)):
            t = list(w[i - 1])
            if i % nk == 0:
                t = t[1:] + t[:1]                         # RotWord
                t = [_SBOX[b] for b in t]                 # SubWord
                t[0] ^= _RCON[i // nk - 1]
            elif nk > 6 and i % nk == 4:
                t = [_SBOX[b] for b in t]                 # SubWord
            w.append([w[i - nk][j] ^ t[j] for j in range(4)])
        return w

    def encrypt_block(self, block):
        s = [list(block[i::4]) for i in range(4)]  # column-major state rows
        # state as 4x4 matrix s[row][col]
        s = [[block[r + 4 * c] for c in range(4)] for r in range(4)]
        self._add_round_key(s, 0)
        for rnd in range(1, self.nr):
            self._sub_bytes(s)
            self._shift_rows(s)
            self._mix_columns(s)
            self._add_round_key(s, rnd)
        self._sub_bytes(s)
        self._shift_rows(s)
        self._add_round_key(s, self.nr)
        return bytes(s[r][c] for c in range(4) for r in range(4))

    def _add_round_key(self, s, rnd):
        for c in range(4):
            word = self.rk[rnd * 4 + c]
            for r in range(4):
                s[r][c] ^= word[r]

    def _sub_bytes(self, s):
        for r in range(4):
            for c in range(4):
                s[r][c] = _SBOX[s[r][c]]

    def _shift_rows(self, s):
        for r in range(1, 4):
            s[r] = s[r][r:] + s[r][:r]

    def _mix_columns(self, s):
        for c in range(4):
            a = [s[r][c] for r in range(4)]
            s[0][c] = _mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3]
            s[1][c] = a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3]
            s[2][c] = a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3)
            s[3][c] = _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)


def ofb_decrypt(key, iv, data):
    aes = AES(key)
    out = bytearray()
    feedback = iv
    i = 0
    while i < len(data):
        feedback = aes.encrypt_block(feedback)
        chunk = data[i:i + 16]
        out.extend(b ^ feedback[j] for j, b in enumerate(chunk))
        i += 16
    return bytes(out)


# Hardcoded key blob from libs/ioI1I1ii1 (Resolver.__init__)
_KEY_BLOB = base64.b64decode(
    b"hTh8uRnL5bX8PZC6Tc3t46nVDFfBpB6Tjw3qazQThpexpg8bLdimevNHj5vJR0nP")


def decrypt_link(link):
    """enlaces_*.link (urlsafe-b64 ciphertext) -> plaintext URL (usually 1fichier)."""
    if not link:
        return None
    if link.startswith("http"):
        return link
    key, iv = _KEY_BLOB[16:], _KEY_BLOB[:16]
    ct = base64.urlsafe_b64decode(link)
    return ofb_decrypt(key, iv, ct).decode("utf-8", "ignore")


if __name__ == "__main__":
    # self-test against the known vector
    sample = "btofTJDt8URHdmR6oLhCjgvRyQTW5T4+I5Q2HgPQIHugp9k8IEkC06vj"
    expect = "https://1fichier.com/?8brt1o8f6btgq6aitvgn"
    got = decrypt_link(sample)
    print("got     :", got)
    print("expected:", expect)
    print("PASS" if got == expect else "FAIL")
