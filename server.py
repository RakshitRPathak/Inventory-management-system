"""Tiny JSON API over http.server (networking). Bearer-token auth + RBAC on every route."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .security import TokenSigner, can
from .service import InventoryError
from .telemetry import TelemetryGateway
from . import rag

def make_handler(svc, signer):
    gw = TelemetryGateway(svc)
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers(); self.wfile.write(body)
        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000: raise ValueError("payload too large")
            return json.loads(self.rfile.read(n) or b"{}")
        def _auth(self, perm):
            tok = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
            claims = signer.verify(tok)
            if not claims: self._send(401, {"error": "unauthenticated"}); return None
            if not can(claims["r"], perm): self._send(403, {"error": "forbidden"}); return None
            return claims
        def _route(self, method):
            try:
                path = self.path.split("?")[0]
                if (method, path) == ("POST", "/login"):
                    b = self._body(); role = svc.authenticate(b.get("username", ""), b.get("password", ""))
                    return self._send(200, {"token": signer.issue(b["username"], role)}) if role else self._send(401, {"error": "bad credentials"})
                if (method, path) == ("GET", "/products"):
                    return self._auth("read") and self._send(200, svc.list_products())
                if (method, path) == ("GET", "/reorder"):
                    return self._auth("read") and self._send(200, svc.reorder_suggestions())
                if (method, path) == ("POST", "/stock"):
                    c = self._auth("adjust")
                    if c: b = self._body(); return self._send(200, {"qty": svc.adjust_stock(b["sku"], int(b["delta"]), b.get("reason", ""), c["u"])})
                    return
                if (method, path) == ("POST", "/telemetry"):
                    c = self._auth("telemetry")
                    if c: return self._send(200, gw.ingest(self._body(), c["u"]))
                    return
                if (method, path) == ("POST", "/ask"):
                    return self._auth("read") and self._send(200, rag.ask(svc, self._body().get("question", "")))
                if (method, path) == ("GET", "/audit/verify"):
                    if self._auth("audit"):
                        ok, bad = svc.audit.verify(); return self._send(200, {"intact": ok, "first_bad_row": bad})
                    return
                self._send(404, {"error": "not found"})
            except InventoryError as e: self._send(409, {"error": str(e)})
            except (KeyError, ValueError, json.JSONDecodeError) as e: self._send(400, {"error": f"bad request: {e}"})
        def do_GET(self): self._route("GET")
        def do_POST(self): self._route("POST")
        def log_message(self, *a): pass
    return H

def serve(svc, host="127.0.0.1", port=8080):
    signer = TokenSigner()
    ThreadingHTTPServer((host, port), make_handler(svc, signer)).serve_forever()
