from shared.config.settings import ConductorSettings


def test_conductor_settings_alias_map(monkeypatch):
    monkeypatch.setenv("FRONTIER_OMLX_BUILDER_URL", "http://builder.local/v1")
    settings = ConductorSettings()

    aliases = settings.alias_map()
    endpoints = settings.omlx_endpoints()

    assert aliases.builder == "builder"
    assert endpoints.builder == "http://builder.local/v1"
    assert endpoints.mem_embed
