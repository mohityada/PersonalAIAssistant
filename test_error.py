import asyncio
from fastapi.testclient import TestClient
from app.main import app
import traceback

try:
    client = TestClient(app)

    response = client.post(
        "/api/v1/search",
        json={"query": "test", "top_k": 5},
        headers={"X-API-Key": "ebc216d2f78bf9778216bc5b00c3b313ef046bdc813bebfab7c2e0bcc13cb0ed"}
    )
    print("STATUS", response.status_code)
    print("BODY", response.text)
except Exception:
    traceback.print_exc()
