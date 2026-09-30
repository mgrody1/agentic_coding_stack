from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from gpt_mcp.config import PROVIDER_DEFAULT_REASONING_EFFORT
from gpt_mcp.provider_child import _request_arguments
from gpt_mcp.provider_process import _encoded_request


class ReasoningEffortRequestTests(unittest.TestCase):
    messages = [{"role": "user", "content": "test"}]

    def _arguments(self, effort: str) -> dict:
        return _request_arguments(
            {"model": "configured-model", "reasoning_effort": effort},
            self.messages,
            [],
        )

    def _encoded_settings(self, *, effort: str | None = None, include: bool = True) -> dict:
        config = SimpleNamespace(
            api_key="sk-test",
            base_url="https://api.gpt.com",
            model="configured-model",
        )
        if include:
            config.reasoning_effort = effort
        payload = json.loads(_encoded_request(config, self.messages, []))
        return payload["settings"]

    def test_none_omits_reasoning_effort(self) -> None:
        arguments = self._arguments("none")
        self.assertNotIn("reasoning_effort", arguments)
        self.assertNotIn("extra_body", arguments)

    def test_low_high_and_max_forward_exact_effort(self) -> None:
        for effort in ("low", "high", "max"):
            with self.subTest(effort=effort):
                arguments = self._arguments(effort)
                self.assertEqual(arguments["reasoning_effort"], effort)
                self.assertNotIn("extra_body", arguments)

    def test_tool_requests_force_none_effort(self) -> None:
        tools = [{"type": "function", "function": {"name": "Read"}}]
        for effort in ("none", "low", "high", "max"):
            with self.subTest(effort=effort):
                arguments = _request_arguments(
                    {"model": "configured-model", "reasoning_effort": effort},
                    self.messages,
                    tools,
                )
                self.assertEqual(arguments["reasoning_effort"], "none")
                self.assertEqual(arguments["tools"], tools)

    def test_missing_effort_keeps_legacy_request_shape(self) -> None:
        settings = self._encoded_settings(include=False)
        self.assertNotIn("reasoning_effort", settings)
        arguments = _request_arguments(settings, self.messages, [])
        self.assertNotIn("reasoning_effort", arguments)
        self.assertNotIn("extra_body", arguments)

    def test_provider_default_marker_keeps_legacy_request_shape(self) -> None:
        settings = self._encoded_settings(effort=PROVIDER_DEFAULT_REASONING_EFFORT)
        self.assertNotIn("reasoning_effort", settings)
        arguments = _request_arguments(settings, self.messages, [])
        self.assertNotIn("reasoning_effort", arguments)
        self.assertNotIn("extra_body", arguments)

    def test_explicit_effort_survives_parent_child_request_boundary(self) -> None:
        for effort in ("none", "low", "high", "max"):
            with self.subTest(effort=effort):
                settings = self._encoded_settings(effort=effort)
                self.assertEqual(settings["reasoning_effort"], effort)
                arguments = _request_arguments(settings, self.messages, [])
                if effort == "none":
                    self.assertNotIn("reasoning_effort", arguments)
                else:
                    self.assertEqual(arguments["reasoning_effort"], effort)
                self.assertNotIn("extra_body", arguments)

    def test_unknown_effort_is_rejected_before_network_call(self) -> None:
        with self.assertRaisesRegex(ValueError, "reasoning effort"):
            self._arguments("ultra")


if __name__ == "__main__":
    unittest.main()
