from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

NS_PAIR = ["ns1.myhost.net", "ns2.myhost.net"]


def error_code(response: Response) -> str:
    code: str = response.json()["error"]["code"]
    return code


def register(client: TestClient, name: str = "shop.com", **body: Any) -> dict[str, Any]:
    response = client.post("/api/v1/domains", json={"name": name, "owner": "alice", **body})
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data
