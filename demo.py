"""Run: python demo.py   -> seeds data, simulates sensors, prints reorder + RAG answers, starts API on :8080"""
import random, time
from inventory.db import connect
from inventory.service import InventoryService
from inventory.telemetry import EdgeNode, TelemetryGateway
from inventory import rag
from inventory.server import serve

conn = connect("inventory.db")
svc = InventoryService(conn)
if not conn.execute("SELECT 1 FROM users").fetchone():
    svc.create_user("admin", "ChangeMe!123", "admin")
    svc.create_user("sensor01", "SensorKey!456", "sensor")
    s = svc.add_supplier("Volt Components", lead_days=5)
    svc.add_product("SKU-001", "PLC Relay Module", "electrical", 40, 15, 12.5, 0.2, "BIN-A1", s)
    svc.add_product("SKU-002", "Ethernet Cable 5m", "networking", 120, 30, 2.1, 0.1, "BIN-B2", s)
    svc.add_product("SKU-003", "Industrial Sensor", "electrical", 18, 10, 45.0, 0.5, "BIN-C3", s)
    now = time.time()
    for d in range(30):                       # 30 days of history so demand forecasting has data
        for sku, mx in (("SKU-001", 2), ("SKU-002", 4), ("SKU-003", 1)):
            q = random.randint(0, mx)
            if q and svc.get(sku)["qty"] >= q: svc.adjust_stock(sku, -q, "sale", "seed", ts=now - d * 86400)

gw, node = TelemetryGateway(svc), EdgeNode("BIN-C3")
for w in [9.0] * 8 + [4.0]:                   # last reading: 5 units vanish from the bin
    msg = node.sample(w)
    if msg: print("sensor ->", gw.ingest(msg))
print("\nReorder suggestions:", svc.reorder_suggestions())
print("\nAsk:", rag.ask(svc, "which items are low on stock?")["answer"])
print("\nAudit chain intact:", svc.audit.verify())
print("\nAPI on http://127.0.0.1:8080  (POST /login first)")
serve(svc)
