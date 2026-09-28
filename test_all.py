import sys, os, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from inventory.db import connect
from inventory.service import InventoryService, InventoryError
from inventory.security import TokenSigner, can, verify_password, hash_password
from inventory.telemetry import EdgeNode, TelemetryGateway
from inventory import rag

def fresh():
    svc = InventoryService(connect())
    s = svc.add_supplier("Acme", 5)
    svc.add_product("A", "Widget", "misc", 20, 5, 2.0, 0.5, "BIN-1", s)
    svc.add_product("B", "Gadget", "misc", 3, 5, 9.0, 1.0, "BIN-2", s)
    return svc

class Stock(unittest.TestCase):
    def test_adjust_and_no_negative(self):
        svc = fresh()
        self.assertEqual(svc.adjust_stock("A", -5), 15)
        with self.assertRaises(InventoryError): svc.adjust_stock("A", -100)
        self.assertEqual(svc.get("A")["qty"], 15)          # unchanged after failed attempt
    def test_unknown_sku(self):
        with self.assertRaises(InventoryError): fresh().adjust_stock("ZZZ", 1)
    def test_low_stock(self):
        self.assertEqual([p["sku"] for p in fresh().low_stock()], ["B"])
    def test_reorder_uses_demand(self):
        svc = fresh(); now = time.time()
        for d in range(10): svc.adjust_stock("A", -1, "sale", ts=now - d * 86400)
        r = {x["sku"]: x for x in svc.reorder_suggestions()}
        self.assertIn("B", r); self.assertGreater(r["B"]["order_qty"], 0)

class Security(unittest.TestCase):
    def test_password(self):
        h, s = hash_password("pw"); self.assertTrue(verify_password("pw", h, s)); self.assertFalse(verify_password("no", h, s))
    def test_token_tamper_and_expiry(self):
        t = TokenSigner(b"k" * 32); tok = t.issue("u", "clerk")
        self.assertEqual(t.verify(tok)["u"], "u")
        self.assertIsNone(t.verify(tok[:-2] + "00"))
        self.assertIsNone(TokenSigner(b"k" * 32, ttl=-1).verify(TokenSigner(b"k" * 32, ttl=-1).issue("u", "x")))
    def test_rbac(self):
        self.assertTrue(can("clerk", "adjust")); self.assertFalse(can("clerk", "audit")); self.assertFalse(can("sensor", "read"))
    def test_audit_chain_detects_tampering(self):
        svc = fresh(); svc.adjust_stock("A", -1)
        self.assertEqual(svc.audit.verify(), (True, None))
        svc.conn.execute("UPDATE audit_log SET detail='forged' WHERE id=2"); svc.conn.commit()
        ok, bad = svc.audit.verify(); self.assertFalse(ok); self.assertEqual(bad, 2)

class Telemetry(unittest.TestCase):
    def test_deadband_suppresses_noise(self):
        n = EdgeNode("BIN-1", deadband=0.5)
        self.assertIsNotNone(n.sample(10.0)); self.assertIsNone(n.sample(10.2))
    def test_edge_anomaly_and_shrinkage_alert(self):
        svc = fresh(); gw = TelemetryGateway(svc); n = EdgeNode("BIN-1")
        for w in [10.0] * 8: n.sample(w)
        msg = n.sample(2.0); self.assertTrue(msg["edge_anomaly"])
        res = gw.ingest(msg); self.assertEqual(res["kind"], "shrinkage")
        self.assertEqual(svc.conn.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"] >= 2, True)
    def test_matching_weight_ok(self):
        svc = fresh(); self.assertEqual(TelemetryGateway(svc).ingest({"bin_id": "BIN-1", "weight": 10.0, "ts": 1})["status"], "ok")
    def test_unknown_bin(self):
        self.assertEqual(TelemetryGateway(fresh()).ingest({"bin_id": "X", "weight": 1, "ts": 1})["kind"], "unknown_bin")

class RAG(unittest.TestCase):
    def test_retrieval_and_fallback(self):
        svc = fresh(); res = rag.ask(svc, "how many gadget do we have", llm=lambda s, u: None)
        self.assertIn("B", res["sources"]); self.assertIn("Gadget", res["answer"])
    def test_llm_prompt_is_grounded(self):
        seen = {}
        rag.ask(fresh(), "widget quantity", llm=lambda s, u: seen.update(s=s, u=u) or "ok")
        self.assertIn("ONLY from the CONTEXT", seen["s"]); self.assertIn("CONTEXT:", seen["u"])
    def test_no_hits(self):
        self.assertEqual(rag.ask(fresh(), "zebra spaceship", llm=lambda s, u: "x")["sources"], [])

if __name__ == "__main__": unittest.main()
