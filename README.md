# Inventory Management System

[![tests](https://github.com/RakshitRPathak/Inventory-management-system/actions/workflows/ci.yml/badge.svg)](https://github.com/RakshitRPathak/Inventory-management-system/actions/workflows/ci.yml)

Run tests: `python -m unittest discover -s tests`  |  Run demo + API: `python demo.py`
Optional LLM answers: `export OPENAI_API_KEY=...` (falls back to offline retrieval without it).

| Resume item | Where it lives |
|---|---|
| SQL / ERP | `db.py` schema, constraints, indexes; `service.py` transactions, reorder logic |
| SCADA / PLC | `telemetry.py` report-by-exception deadband, book-vs-sensed reconciliation |
| Edge AI / IoT (mine tremor patent) | `telemetry.py` EdgeNode rolling z-score anomaly detection |
| Networking | `server.py` REST API, bearer auth, payload limits |
| Cybersecurity | `security.py` PBKDF2, RBAC, signed tokens, hash-chained audit log |
| Audit (IS audit patent / CBS3015) | `AuditLog.verify()` tamper-evident trail |
| LLM / RAG / OpenAI / prompts | `rag.py` TF-IDF retrieval, grounded prompt, injection-aware system prompt |
| Testing (aiDataWorks QA) | `tests/test_all.py` 15 tests: edge cases, tamper, failure paths |

## API
POST /login -> token | GET /products | GET /reorder | POST /stock | POST /telemetry | POST /ask | GET /audit/verify
