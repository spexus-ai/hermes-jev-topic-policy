# Jev Topic Policy for Hermes

Standalone plugin for a stateless, document-only Telegram bot. Hermes owns required
gate execution; this plugin owns topic classification through the direct Jev API.

- Plugin repository: https://github.com/spexus-ai/hermes-jev-topic-policy
- Patched Hermes: https://github.com/spexus-ai/hermes-agent
- [Example configuration](examples/config.yaml)
- [Topic policy](examples/topic-policy.yaml)
- [Example document corpus](examples/documents.json)

Clone both repositories before installation or a Docker build:

```sh
git clone https://github.com/spexus-ai/hermes-agent.git
git clone https://github.com/spexus-ai/hermes-jev-topic-policy.git
cd hermes-jev-topic-policy
```

Requires the accompanying Hermes core changes (`PluginContext.register_message_gate`,
`agent.message_gates`, `document_qa` gateway mode). Unmodified upstream Hermes does
not support this plugin. No real corpus or production-calibrated topic policy is
included: the examples are explicitly experimental.

## What runs

```
Telegram text → authorization / limits → documents + question
  → required input gates → one non-streaming Chat Completions request
  → required output gates → plain-text Telegram send
```

Normally two Jev calls, each with three classification questions: in-scope,
prohibited content, override. Input rejection makes no task-model call. Exceptions,
missing scores, malformed responses and timeouts fail closed. Output rejection
never sends the generated text. Refusals are operator-approved static templates.

The task-model sees the complete small corpus (UTF-8 JSON ≤48 KB, ≤100 documents).
There is no embedding service, retrieval tool, autonomous AIAgent loop, history,
memory sync, shell, MCP, auxiliary model, response streaming or TTS in this mode.
Only HTTPS OpenAI-compatible Chat Completions is supported; Responses, proxy, MoA
and other agent modes are not covered. This deliberately small execution path
implements the supported mode instead of claiming protection for all Hermes APIs.

## Local installation

Use a **new, standalone Hermes profile** with no owner data. With that profile's
`HERMES_HOME` set:

```sh
mkdir -p "$HERMES_HOME/plugins"
cp -R jev-topic-policy "$HERMES_HOME/plugins/jev-topic-policy"
cp examples/documents.json "$HERMES_HOME/documents.json"
cp examples/topic-policy.yaml "$HERMES_HOME/topic-policy.yaml"
```

Merge `examples/config.yaml` into the new profile's config. It uses the real native
plugin settings location: `plugins.entries.jev-topic-policy.settings`. Replace
`REPLACE_WITH_CHAT_COMPLETIONS_MODEL`, corpus and allowed scope. Configure Telegram
through Hermes' existing setup and access controls. Only Telegram may be enabled.

Required gateway settings:

```yaml
gateway:
  multiplex_profiles: false
group_sessions_per_user: true
thread_sessions_per_user: true
```

Put credentials in the profile's `.env` or inject them into the container:

```
TELEGRAM_BOT_TOKEN=<bot credential>
TELEGRAM_ALLOWED_USERS=<test Telegram numeric user ID>
TYPESAFE_API_KEY=<Jev credential>
OPENAI_API_KEY=<task-model credential>
```

Start with `hermes gateway run` from the patched Hermes environment. Startup checks
the corpus, credentials, required async gate registrations and supported mode.
The model endpoint is a full URL ending in `/chat/completions`. The endpoint and
model are configured under `document_qa`, independently of the ordinary agent's
model selection. No automatic fallback or credentialed redirects occur.

All documents must be suitable for **every** chat participant and for transmission
to both Jev and the task-model provider. Requests are independent; reply context
and channel backfill are ignored. Commands/attachments receive static refusals;
the text-only adapter does not download media or register interactive callbacks.
One pending follow-up per session and 16 globally are retained without merging;
additional busy input is rejected. Ordinary adapter draining re-enters the same gates.

Configuration, corpus and topic policy are pinned until restart. Memory, background
agent recovery, cron and agent warmup are not started in document mode. Telegram
transport reconnection remains enabled. Do not run a separate CLI/cron/API process
in this profile: the plugin API does not retrofit guards into those entry points.

## Calibrate before public use

`examples/topic-policy.yaml` has `calibrated: false` and illustrative thresholds.
`experimental: true` permits isolated testing only. Build an independent holdout
with valid product questions, no-evidence questions, political requests, mixed
requests, roleplay, multilingual attacks and ambiguous terms (e.g. “data policy”).
Measure input false refusals and **actual output** off-topic escapes separately.
After calibration, set the approved thresholds, increment policy/question versions,
mark `calibrated: true`, remove experimental mode and restart.

The `calibrated` flag is an operator attestation, not an automated proof. The included
tests validate enforcement and parsing with fake HTTP responses, not Jev's semantic
accuracy. A low classifier score is not a mathematical guarantee. Citation existence
is checked, but factual entailment of the answer is not established by that check.

## Container

`compose.yaml` builds the **local patched Hermes checkout**, not an unpatched release:

```sh
HERMES_SOURCE=/absolute/path/to/hermes-agent docker compose build
HERMES_SOURCE=/absolute/path/to/hermes-agent docker compose up
```

Export the four credentials above first. Adjust the example config to enable Telegram
using its standard configuration if your setup requires it. The container is non-root,
read-only, drops Linux capabilities, has CPU/memory/PID limits and keeps runtime state
in tmpfs. Configuration, corpus and plugin are read-only mounts. No host socket is mounted.

Docker's default bridge **does not enforce a destination allowlist**. Deploy behind an
egress firewall/proxy allowing only Telegram, Jev and your model provider if that network
property is required. The application HTTP clients disable redirects and ambient proxies.

## Tests

From the patched Hermes checkout (dev dependencies installed):

```sh
scripts/run_tests.sh tests/agent/test_message_gates.py \
  tests/hermes_cli/test_required_message_gate_plugins.py \
  tests/gateway/test_document_qa.py \
  /absolute/path/to/hermes-jev-topic-policy/tests/test_plugin.py
```

No production credentials, paid calls or live Telegram messages are used by these tests.
