import httpx

from shared.clients.worker_client import WorkerClient


def test_worker_client_health_mocked():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)

    client = WorkerClient(base_url="http://worker", token="t", http_client=http_client)
    response = client.health()

    assert response["status"] == "ok"
