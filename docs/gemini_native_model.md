# Native Gemini model

This checkout provides `siada.provider.gemini.GeminiModel`, an Agents `Model`
implemented with the official `google-genai` SDK. Native Gemini requests do not
use the LiteLLM bridge. The existing `default` and `li` providers select this
model for native Gemini routes; non-Gemini routes are unchanged.

Derived names of the form `xxx-gemini` or `xxx-gemini-*` are supported for any
hyphenated prefix, such as `google-gemini-3.5-flash` or
`my-team-gemini-3.5-flash`. Native requests remove the alias prefix and use
`gemini-3.5-flash` as the model ID. Matching is case-insensitive and preserves
the model ID's casing. OpenRouter takes priority: when the default provider's
effective `BASE_URL` points to OpenRouter, these names retain the OpenRouter
compatibility route rather than switching to native Gemini. Explicit
`openrouter/...` routing and existing endpoint validation are unchanged.

## Default provider configuration

Set `GEMINI_API_KEY` or `GOOGLE_API_KEY`. `API_KEY` remains a fallback. Use
`GEMINI_BASE_URL` for a native Gemini endpoint when `BASE_URL` is already set
to an OpenAI Chat endpoint. A native endpoint can include its `/v1beta` prefix.
Do not point this adapter at a `/chat/completions` endpoint.

OpenRouter remains a compatibility route and is outside the native signature
preservation guarantee. Use a native Gemini endpoint for lossless Part replay.
The Li route reuses the application's existing authentication and routing;
its actual gateway passthrough still requires separate live validation.

## Explicit model and client ownership

The caller can inject an official client. The caller owns that client and must
close it after all requests have finished:

```python
import asyncio
import os

from agents import Agent, RunConfig, Runner
from google import genai

from siada.provider.gemini import GeminiModel


async def main():
    client = genai.Client(vertexai=False, api_key=os.environ["GEMINI_API_KEY"])
    try:
        model = GeminiModel("gemini-3.5-flash", client=client)
        agent = Agent(name="Gemini assistant", model=model)
        result = await Runner.run(
            agent, "Hello", run_config=RunConfig(tracing_disabled=True)
        )
        print(result.final_output)
    finally:
        await client.aio.aclose()
        client.close()


asyncio.run(main())
```

Without an injected client or transport, `GeminiModel` owns its default
transport; call `await model.close()` when finished. Models returned by an
application provider borrow that provider's connections. Close the provider,
not each model, at runtime shutdown. Do not reuse asynchronous connections on
another event loop.

## History and supported settings

For uncompressed replay, preserve complete SDK input items, including their
opaque provider metadata. The provider restores the original signed fragments
for text, reasoning and function calls; the agents framework only processes
standard SDK items. Do not rebuild retained items from display text or modify
their signed text/tool arguments. Native signed replay requires the same
Gemini model, provider and backend. Other models can consume the standard
history, including for summarization, without using Gemini's private metadata.

When switching from another model to Gemini, completed SDK function-call history
without a Gemini envelope is accepted. Each call needs a unique, nonempty
`call_id`, arguments containing a JSON object, and a matching textual result.
The adapter supplies Google's documented `skip_thought_signature_validator`
marker for these imported calls. Existing native `apply_patch` and custom tool
history can also be imported through function-call proxies.

Import conversion happens when building a request and leaves stored history
intact. Adjacent unsigned calls and results form one call group followed by one
result group, including interleaved parallel pairs. Assistant or reasoning
messages separate completed steps. This compatibility path skips signature
validation; it cannot recover the previous model's thought state or missing
original Part and response-group boundaries. Existing Gemini signatures are
replayed unchanged, and invalid native versions, origins, signed views or
incomplete parallel tool groups still fail before a request is sent.
See Google's [thought signature migration FAQ](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures).

Runner owns function execution. Google automatic function calling is disabled.
The adapter supports unnamespaced function tools, complete function calls,
textual tool results, text/reasoning output, user text/images and JSON output
schemas. It rejects hosted tools, partial streaming function arguments,
generated images/audio, and server-owned Responses conversation state.

Use ordinary `ModelSettings` for temperature, top-p, output tokens, tool choice
and timeout. Use official `GenerateContentConfig` field names in `extra_body`
or `extra_args` for native options, such as `thinking_config`. Ownership fields
such as tools, history, credentials and HTTP options cannot be overridden there.
`ModelSettings.reasoning.effort` maps to thinking levels on Gemini 3 and 4 models;
older models should use native thinking configuration. `effort="none"` sends
zero thinking budget; whether that disables thinking depends on the selected
Google model. Request `reasoning.summary` to include thought text.

Gemini uses the same configured compaction strategy as other models, including
header summaries, recent-boundary retention and complete tool-group pruning.
Compaction may discard older items; each retained item keeps its own signed
fragments, and the provider restores their original order and parallel-call
grouping after session reload or checkpoint restoration. An existing signed
Part is never replaced with a validation-bypass marker. Local token budgets
are approximate UTF-8 byte estimates, not native tokenizer counts; actual usage
remains available for calibration. Generation spans contain model metadata and
usage only; telemetry excludes provider metadata. Treat session files as sensitive.
