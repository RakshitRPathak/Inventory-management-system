# Inventory Management System

[![tests](https://github.com/RakshitRPathak/Inventory-management-system/actions/workflows/ci.yml/badge.svg)](https://github.com/RakshitRPathak/Inventory-management-system/actions/workflows/ci.yml)

Run tests: `python -m unittest discover -s tests`  |  Run demo + API: `python demo.py`
Optional LLM answers: `export OPENAI_API_KEY=...` (falls back to offline retrieval without it).

## API
POST /login -> token | GET /products | GET /reorder | POST /stock | POST /telemetry | POST /ask | GET /audit/verify
