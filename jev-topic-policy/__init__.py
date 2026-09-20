"""Standalone Hermes plugin; no monkeypatching or vendor-specific core imports."""

from pathlib import Path

import yaml

from .policy import JevTopicPolicy


def register(ctx):
    from hermes_constants import get_hermes_home
    from agent.secret_scope import get_secret

    path = Path(ctx.get_config("policy_file", "topic-policy.yaml"))
    if not path.is_absolute():
        path = get_hermes_home() / path
    with path.open("rb") as file:
        raw = file.read(32769)
    if len(raw) > 32768:
        raise ValueError("Topic policy exceeds limit")
    config = yaml.safe_load(raw)
    key_name = ctx.get_config("api_key_env", "TYPESAFE_API_KEY")
    policy = JevTopicPolicy(config, api_key=get_secret(key_name) or "",
                            experimental=ctx.get_config("experimental", False))
    ctx.register_message_gate("before_model_request", policy.evaluate)
    ctx.register_message_gate("before_response_delivery", policy.evaluate)
