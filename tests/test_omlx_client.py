import httpx

from shared.clients.omlx_client import OMLXClient
from shared.config.settings import ConductorSettings


def test_omlx_embed_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    settings = ConductorSettings(api_token="t", omlx_mem_embed_url="http://mock/v1")

    client = OMLXClient(settings=settings, http_client=http_client)
    result = client.embed("mem-embed", ["hello"])

    assert result == [[1.0, 0.0]]
