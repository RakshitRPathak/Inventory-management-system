"""SCADA/PLC-style telemetry + edge analytics (resume: SCADA/PLC, IoT edge-AI mine-tremor work).

Smart bins report weight. Two ideas borrowed from industrial systems:
  1. Report-by-exception (deadband): the edge node only transmits when the value moves enough.
  2. Rolling z-score anomaly detection at the edge to catch sudden drops (theft/spill/sensor fault).
The gateway then reconciles sensor-derived quantity with the ERP book quantity.
"""
import math, time
from collections import deque

class EdgeNode:
    def __init__(self, bin_id, deadband=0.5, window=20, z_threshold=3.5):
        self.bin_id, self.deadband, self.z = bin_id, deadband, z_threshold
        self.window = deque(maxlen=window)
        self.last_sent = None

    def sample(self, weight, ts=None):
        """Return a message to transmit, or None if suppressed by the deadband."""
        ts = ts or time.time()
        anomaly = self._is_anomaly(weight)
        self.window.append(weight)
        if self.last_sent is not None and abs(weight - self.last_sent) < self.deadband and not anomaly:
            return None
        self.last_sent = weight
        return {"bin_id": self.bin_id, "weight": weight, "ts": ts, "edge_anomaly": anomaly}

    def _is_anomaly(self, w):
        n = len(self.window)
        if n < 5: return False
        mean = sum(self.window) / n
        var = sum((x - mean) ** 2 for x in self.window) / n
        std = max(math.sqrt(var), 0.25)          # floor so a flat signal isn't hypersensitive
        return abs(w - mean) / std > self.z

class TelemetryGateway:
    def __init__(self, service, tolerance_units=1):
        self.svc, self.tol = service, tolerance_units

    def ingest(self, msg, user="sensor"):
        conn = self.svc.conn
        p = conn.execute("SELECT * FROM products WHERE bin_id=?", (msg["bin_id"],)).fetchone()
        if not p:
            self._alert(msg, None, "unknown_bin", "no product mapped to bin")
            return {"status": "alert", "kind": "unknown_bin"}
        sensed = round(msg["weight"] / p["unit_weight"])
        diff = sensed - p["qty"]
        if msg.get("edge_anomaly"):
            self._alert(msg, p["sku"], "edge_anomaly", f"sudden weight change to {msg['weight']}kg")
        if abs(diff) > self.tol:
            kind = "shrinkage" if diff < 0 else "unrecorded_receipt"
            self._alert(msg, p["sku"], kind, f"book={p['qty']} sensed={sensed} diff={diff:+d}")
            return {"status": "alert", "kind": kind, "diff": diff}
        conn.commit()
        return {"status": "ok", "diff": diff}

    def _alert(self, msg, sku, kind, detail):
        self.svc.conn.execute("INSERT INTO alerts(ts,bin_id,sku,kind,detail) VALUES(?,?,?,?,?)",
                              (msg["ts"], msg["bin_id"], sku, kind, detail))
        self.svc.audit.record("sensor", "alert:" + kind, f"{msg['bin_id']} {detail}")
        self.svc.conn.commit()
