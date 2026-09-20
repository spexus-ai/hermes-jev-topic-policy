"""Real plugin discovery and both HTTP boundaries; no external credentials or network."""

import json
from pathlib import Path
import shutil

import httpx
import pytest
import yaml

from agent.gated_chat import GatedChat, RequestIdentity
from agent.message_gates import RequiredGates
from hermes_cli.plugins import PluginManager

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def installed(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-jev-key")
    shutil.copytree(ROOT / "jev-topic-policy", tmp_path / "plugins" / "jev-topic-policy")
    policy = yaml.safe_load((ROOT / "examples" / "topic-policy.yaml").read_text())
    # Test transport only; this flag is not a production calibration claim.
    policy["calibrated"] = True
    (tmp_path / "topic-policy.yaml").write_text(yaml.safe_dump(policy))
    cfg = yaml.safe_load((ROOT / "examples" / "config.yaml").read_text())
    cfg["plugins"]["entries"]["jev-topic-policy"]["settings"]["experimental"] = False
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg))
    manager = PluginManager()
    manager.discover_and_load()
    loaded = manager._plugins["jev-topic-policy"]
    assert loaded.enabled, loaded.error
    try:
        yield manager, cfg, loaded.module
    finally:
        manager.unload()


@pytest.mark.asyncio
@pytest.mark.parametrize("case,expected_models,expected_jev", [
    ("allow", 1, 2), ("input_deny", 0, 1), ("output_deny", 1, 2),
    ("malformed", 0, 1), ("missing", 0, 1), ("nan", 0, 1), ("bool", 0, 1),
    ("429", 0, 1), ("redirect", 0, 1), ("model_tool_call", 1, 1),
])
async def test_plugin_controls_real_request_and_delivery(installed, monkeypatch, case,
                                                          expected_models, expected_jev):
    manager, cfg, _ = installed
    requests, sent = [], []

    def remote(request):
        body = json.loads(request.content)
        requests.append((request.url.host, body))
        if request.url.host == "api.typesafe.ai":
            assert request.headers["authorization"] == "Bearer fake-jev-key"
            assert set(body["questions"]) == {"in_scope", "prohibited", "override"}
            stage = json.loads(body["state"])["stage"]
            if case == "429":
                return httpx.Response(429, text="private-provider-error")
            if case == "redirect":
                return httpx.Response(307, headers={"location": "https://attacker.invalid/steal"})
            if case == "malformed":
                return httpx.Response(200, text="not-json")
            scores = {"in_scope": .99, "prohibited": .01, "override": .01}
            if case == "input_deny" or (case == "output_deny" and stage == "before_response_delivery"):
                scores["prohibited"] = .99
            if case == "nan":
                scores["in_scope"] = "NaN"
            if case == "bool":
                scores["in_scope"] = True
            if case == "missing":
                scores.pop("override")
            return httpx.Response(200, json={"answers": {k: {"probability": v} for k, v in scores.items()}})
        assert request.url.host == "model.test"
        assert request.headers["authorization"] == "Bearer fake-model-key"
        assert "tools" not in body
        message = {"content": "Install X. [source:manual]"}
        if case == "model_tool_call":
            message["tool_calls"] = [{"function": {"name": "terminal", "arguments": "{}"}}]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": message}]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(remote), **kwargs))

    async def send(text):
        sent.append(text)

    gates = RequiredGates(cfg["message_gates"], manager._message_gates)
    await GatedChat(gates=gates, endpoint="https://model.test/v1/chat/completions", model="test",
                    api_key="fake-model-key", policy_version="product-x-v1").answer(
        identity=RequestIdentity("home", "alice", "chat", "destination"), question="Install X?",
        documents=[{"id": "manual", "title": "Install", "text": "Install X."}],
        corpus_version="v1", send=send)
    assert sum(host == "model.test" for host, _ in requests) == expected_models
    assert sum(host == "api.typesafe.ai" for host, _ in requests) == expected_jev
    assert len(sent) == 1
    assert (sent[0] == "Install X. [source:manual]") == (case == "allow")
    assert "private-provider-error" not in sent[0]


def test_missing_calibration_refuses_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake")
    shutil.copytree(ROOT / "jev-topic-policy", tmp_path / "plugins" / "jev-topic-policy")
    shutil.copy(ROOT / "examples" / "topic-policy.yaml", tmp_path / "topic-policy.yaml")
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"plugins": {"enabled": ["jev-topic-policy"]}}))
    manager = PluginManager()
    try:
        manager.discover_and_load()
        assert not manager._message_gates
        assert not manager._plugins["jev-topic-policy"].enabled
    finally:
        manager.unload()
