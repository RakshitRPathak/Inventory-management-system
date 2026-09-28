"""Cybersecurity layer: salted PBKDF2, RBAC, signed tokens, tamper-evident audit chain."""
import hashlib, hmac, json, os, time, base64

ITERATIONS = 200_000
PERMISSIONS = {
    "admin":   {"read", "write", "adjust", "telemetry", "audit", "users"},
    "manager": {"read", "write", "adjust", "audit"},
    "clerk":   {"read", "adjust"},
    "sensor":  {"telemetry"},          # least privilege for edge devices
}

def hash_password(password: str, salt: bytes = None):
    salt = salt or os.urandom(16)
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS), salt

def verify_password(password, pw_hash, salt):
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, pw_hash)   # constant-time compare

def can(role, permission):
    return permission in PERMISSIONS.get(role, set())

class TokenSigner:
    """Minimal HMAC-signed token (JWT-like). Use a real JWT lib in production."""
    def __init__(self, secret: bytes = None, ttl=3600):
        self.secret, self.ttl = secret or os.urandom(32), ttl
    def issue(self, username, role):
        body = base64.urlsafe_b64encode(json.dumps(
            {"u": username, "r": role, "exp": time.time() + self.ttl}).encode())
        sig = hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        return f"{body.decode()}.{sig}"
    def verify(self, token):
        try:
            body, sig = token.rsplit(".", 1)
            good = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, good):
                return None
            data = json.loads(base64.urlsafe_b64decode(body))
            return data if data["exp"] > time.time() else None
        except Exception:
            return None

class AuditLog:
    """Hash-chained log: editing or deleting any row breaks verify()."""
    GENESIS = "0" * 64
    def __init__(self, conn): self.conn = conn
    def _last_hash(self):
        r = self.conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        return r["hash"] if r else self.GENESIS
    @staticmethod
    def _digest(prev, ts, user, action, detail):
        return hashlib.sha256(f"{prev}|{ts}|{user}|{action}|{detail}".encode()).hexdigest()
    def record(self, user, action, detail=""):
        prev, ts = self._last_hash(), time.time()
        h = self._digest(prev, ts, user, action, detail)
        self.conn.execute("INSERT INTO audit_log(ts,user,action,detail,prev_hash,hash) VALUES(?,?,?,?,?,?)",
                          (ts, user, action, detail, prev, h))
    def verify(self):
        prev = self.GENESIS
        for r in self.conn.execute("SELECT * FROM audit_log ORDER BY id"):
            if r["prev_hash"] != prev or r["hash"] != self._digest(prev, r["ts"], r["user"], r["action"], r["detail"]):
                return False, r["id"]
            prev = r["hash"]
        return True, None
