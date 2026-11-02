# Consumer Apps — Plugging a Private App into Bob-API

Bob-api exposes an internal HMAC-authenticated channel that lets a separately
deployed application drive labs, GPU workflows, LLMs, STT, and ffmpeg ops
without sharing a process or a database. Use it to build user-facing products
on top of bob-api's heavy lifting while keeping the two systems independently
deployable.

## Why a separate consumer app?

Run user-facing products that own their own data — accounts, billing, app-
specific tables — while reusing bob-api's heavy lifting:

- Lab orchestration (multi-agent, tools, sandboxes)
- LLM dispatcher with load balancing across providers
- ComfyUI workflow execution (Flux, LTX, etc.)
- STT, ffmpeg, video rendering

The consumer app stays small. Bob-api stays generic. The boundary is a few
HTTP endpoints behind a per-app HMAC secret.

## Registering an app

bob-ui → Admin → Consumer Apps → "Create app." Pick a slug (e.g. `myapp`),
the UI returns a freshly generated HMAC secret **once**. Copy it into the
consumer app's `.env`:

```env
BOB_API_URL=http://bob-api:8000
BOB_APP_ID=myapp
BOB_APP_SECRET=<hex64 from bob-ui>
```

Bob-api stores only the bcrypt hash. Revoke or rotate from the same admin UI.

## Authenticating a request

Every request signs the body with HMAC-SHA256:

```text
message  = "<unix_seconds>.<raw_body_bytes>"
signature = hex(hmac_sha256(BOB_APP_SECRET, message))
```

Headers on every call:

```http
Content-Type: application/json
X-App-Id:        <slug>
X-App-Timestamp: <unix_seconds>
X-App-Signature: <hex>
```

Bob-api rejects:

- missing or unknown `X-App-Id` → 401
- timestamp drift > **300 s** → 401 (replay protection)
- signature mismatch → 401
- revoked key → 401

A reference signer in Python:

```python
import hmac, hashlib, time, json, httpx

def call(path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    sig = hmac.new(
        BOB_APP_SECRET.encode(),
        ts.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    r = httpx.post(
        f"{BOB_API_URL}{path}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-App-Id": BOB_APP_ID,
            "X-App-Timestamp": ts,
            "X-App-Signature": sig,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
```

## Endpoints

All paths live under `/api/v1/internal/apps/*`.

### Lab lifecycle

| Endpoint | Purpose |
|---|---|
| `POST /import_lab` | Idempotent import of a lab blueprint (JSON). Tags it `acl.tag=app:<app_id>:template:<name>` so it's hidden from the operator UI. Returns the lab id. |
| `POST /run_lab` | Clone a template lab, seed `context_files`, run agents, copy named `output_artifacts` to the shared volume, post a callback. |

### Direct GPU dispatchers (skip the agent loop)

| Endpoint | Purpose |
|---|---|
| `POST /run` | Submit a ComfyUI workflow JSON, wait for completion, copy outputs. |
| `POST /run_flux_text2img` | Convenience wrapper for Flux.1-Dev. |
| `POST /run_ltx_image2video` | Convenience wrapper for LTX-2.3. |
| `POST /run_ffmpeg_op` | Local ffmpeg ops: `extract_last_frame`, `concat`. |

### Model proxies

| Endpoint | Purpose |
|---|---|
| `POST /transcribe` | STT dispatcher (Whisper). Returns text + per-segment timestamps. |
| `POST /llm_complete` | One-shot or multi-turn chat completion. Routed by the bob-api dispatcher to the least-loaded compatible provider. Pass `model`, `messages` (full conversation history), `temperature`, optional `max_tokens` (default 4096, see below). Stateless — your app holds the conversation state and replays it each turn. No lab needed. Vision-capable models accept image attachments (see below). Function calling is supported via the optional `tools` field (see below). Ollama reasoning models accept `think: false` to skip chain-of-thought (see below). |
| `POST /list_models` | Discover the model identifiers that `/llm_complete` can route to. Body: `{"available_only": true}` (default). Returns `{models: [{model_identifier, available, provider_types, capabilities}]}`. |

### Sending images to a vision model

`/llm_complete` accepts an optional `images` field on any user message. Each
entry is a base64-encoded image (raw, or with a `data:image/...;base64,`
prefix). The dispatcher converts to provider-native format automatically:
Ollama sees the native `images` field; OpenAI-compatible providers (vLLM,
HuggingFace TGI) get OpenAI multimodal `content_parts`.

Pick a vision-capable model (e.g. `kavai/qwen3.5-GPT5:9b`, `llava:*`,
`qwen2-vl:*`). Models without vision support will ignore the images or error.

```json
{
  "model": "kavai/qwen3.5-GPT5:9b",
  "messages": [
    {
      "role": "user",
      "content": "Describe what you see in one sentence.",
      "images": ["iVBORw0KGgoAAAANSUhEUgAA..."]
    }
  ],
  "temperature": 0.1,
  "max_tokens": 300
}
```

A few practical notes:

- The HMAC body signature still covers the entire request, so the image is
  authenticated alongside the prompt. No separate upload step.
- Larger images mean larger bodies and slower HMAC + bigger token counts on
  the model side. Resize/compress on the consumer side before encoding.
- Conversation history is replayed every turn (stateless). If your chat
  references an earlier image, send it again on each turn.

### Controlling output length (`max_tokens`)

`max_tokens` caps how many tokens the model is allowed to generate in a
single response. Default is **4096**. Lower it to fit a UI snippet, raise it
for long-form output. Generation stops as soon as the limit is hit, which
means the response can end mid-sentence — your app should treat it as a
hard ceiling.

```json
{
  "model": "qwen3.6:35b-a3b",
  "messages": [{"role": "user", "content": "Write a 200-word essay on tea."}],
  "max_tokens": 32
}
```

Live numbers on the same prompt:

| `max_tokens` | tokens out | duration | content end |
|---:|---:|---:|---|
| `32` | 32 | 2.8 s | `…become a cultural cornerstone and a symbol of tranquility. Originating in ancient` (truncated) |
| `4096` | 326 | 25.0 s | `…uniting people across borders through its gentle, enduring warmth.` (complete) |

Per-provider behavior:

- **Ollama**: forwarded as `options.num_predict`. Hard ceiling; the model
  stops emitting tokens at the limit.
- **vLLM / HuggingFace TGI**: forwarded as `max_tokens`, but auto-capped to
  the model's `max_model_len` (queried from `/v1/models` and cached) to
  avoid 4xx errors when you ask for more than the context window allows.
  The cap is silent — `tokens_out` will reflect the actual generated count.
- **OpenAI-compatible providers**: forwarded as `max_tokens` verbatim.
- **Anthropic**: forwarded as `max_tokens` verbatim.

A few practical notes:

- Input tokens (`tokens_in`) are not bounded by this field — only the
  output side is capped. If your conversation history is huge, you'll pay
  for it on the input side regardless of `max_tokens`.
- For reasoning models with `think: true`, the chain-of-thought counts
  toward `max_tokens`. If you ask for `max_tokens: 100` on a reasoning
  model, you may exhaust the budget before the final answer starts. Either
  raise it, or set `think: false` (Ollama only).
- Tool-calling responses (`tool_calls`) also count toward the token budget.

### Disabling reasoning (Ollama `think` flag)

Reasoning models served by Ollama (qwen3, deepseek-r1, gpt-oss, etc.) emit a
chain-of-thought before the final answer. For latency-sensitive or cost-
sensitive consumer-app calls, pass `think: false` to skip it:

```json
{
  "model": "qwen3.6:35b-a3b",
  "messages": [{"role": "user", "content": "What is 17 * 23?"}],
  "think": false
}
```

Live numbers on the same prompt against `qwen3.6:35b-a3b`:

| `think` | tokens out | duration | content |
|---|---:|---:|---|
| `false` | 4 | 14.4 s | `"391"` |
| `true` | 268 | 20.6 s | reasoning trace + answer |

Accepted values: `true`, `false`, or `"low"` / `"medium"` / `"high"` for
`gpt-oss`-style models that support graded reasoning. Omit the field to
keep the model's default behaviour.

The flag is **Ollama-only**. vLLM, HuggingFace TGI, OpenAI-compat, and
Anthropic providers silently ignore it — calls don't fail, the field is
just dropped. If you need to suppress reasoning on a non-Ollama provider,
do it via the system prompt instead.

### Function calling (tools)

`/llm_complete` accepts an optional `tools` list using the OpenAI function-
calling schema. Bob-api forwards it to the provider in the right native
format (Ollama's `tools` field for Ollama, OpenAI multipart for vLLM / HF
TGI). When the model decides to call a function, the response includes a
`tool_calls` list — your app dispatches the call, appends the result as a
`{role: "tool", ...}` message, and replays the conversation.

Request:

```json
{
  "model": "qwen3.6:35b-a3b",
  "messages": [
    {"role": "system", "content": "Use tools when relevant."},
    {"role": "user",   "content": "Weather in Paris and Tokyo?"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
          "type": "object",
          "properties": {"city": {"type": "string"}},
          "required": ["city"]
        }
      }
    }
  ],
  "temperature": 0.1
}
```

Response (when the model emits tool calls):

```json
{
  "content": "...optional reasoning text...",
  "model": "qwen3.6:35b-a3b",
  "provider": "7950x-agent",
  "tokens_in": 299,
  "tokens_out": 94,
  "duration_ms": 23829,
  "tool_calls": [
    {"id": "call_0", "name": "get_weather", "arguments": {"city": "Paris"}},
    {"id": "call_1", "name": "get_weather", "arguments": {"city": "Tokyo"}}
  ]
}
```

Notes:

- The shape is **flat** (`{id, name, arguments}` with `arguments` already
  parsed as a dict), not OpenAI's nested
  `{id, type:"function", function:{name, arguments:"<json string>"}}`.
- If the model returns malformed argument JSON, `arguments` is
  `{"raw_arguments": "<original string>"}` so the call is still inspectable.
- `content` may still contain free-text reasoning the model emitted before
  deciding to call the tool. Treat both fields as available simultaneously.
- A provider that doesn't support tool calling (e.g. vLLM without
  `--enable-auto-tool-choice`) is detected and the call is transparently
  retried without `tools`. In that case `tool_calls` will be absent and the
  model's plain-text reply lands in `content`.
- `tool_calls` is only present when the model emitted at least one call.
  Existing callers that ignore the field see no behavioral change.

To continue the conversation after running the tool, append the assistant's
turn (with its `tool_calls`) and one `tool` message per call:

```json
[
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "", "tool_calls": [...]},
  {"role": "tool", "tool_call_id": "call_0", "content": "{\"temp_c\": 18}"},
  {"role": "tool", "tool_call_id": "call_1", "content": "{\"temp_c\": 24}"}
]
```

## Webhook callbacks

Long-running endpoints (lab runs, ComfyUI dispatches) accept a `callback_url`
and respond immediately. When the work finishes, bob-api POSTs back to that
URL with the same HMAC-signed envelope (using **the consumer app's secret** —
mutual auth):

```json
{
  "generation_id": "<your-uuid>",
  "status": "completed | failed",
  "output_path": "/data/app_uploads/<app_id>/<generation_id>/<file>",
  "error": "..."
}
```

Retry policy: 3 attempts with exponential backoff (~14 s total). After that,
bob-api logs and drops; the consumer app must reconcile via a sweeper or
admin tool.

## Shared filesystem

Generation artifacts are written to a named Docker volume mounted on **both**
containers:

- bob-api: `/data/app_uploads/<app_id>/...` (RW)
- consumer-api: same path (RO is sufficient)

The consumer app reads files directly from disk. There is no HTTP file
endpoint — the named volume is the contract.

## ACL tags

Bob-api tags every lab created on behalf of a consumer app:

- Templates: `app:<app_id>:template:<name>`
- Runs: `app:<app_id>:run:<generation_id>`

The operator-facing `GET /api/v1/labs` filters out anything matching
`app:*` by default. Pass `?include_app_runs=true` to surface them for
debugging.

## Filesystem layout for a consumer-app repo

The recommended shape:

```
my-consumer-app/
├── app-api/                     # FastAPI backend (your business logic)
│   └── app/
│       ├── services/bob_client.py   # HMAC client to bob-api
│       └── api/routes/...           # endpoints your UI calls
├── app-ui/                      # React/Next/whatever frontend
├── docker-compose.yml           # joins bob-api's network as external
├── .env.example                 # BOB_API_URL, BOB_APP_ID, BOB_APP_SECRET
└── README.md
```

The compose file should:

- declare bob-api's network as `external: true`
- declare the `app_uploads` volume as `external: true`
- mount the volume into your container at the same path bob-api uses

## What does NOT cross the boundary

The consumer app **must not** reach into bob-api's database, Qdrant, or lab
filesystem directly. Everything goes through the documented HTTP surface.
This keeps bob-api releasable and upgrade-safe.

If you find yourself wanting a primitive that doesn't exist yet, the right
move is to add a generic endpoint to bob-api — not a special case for your
app.

## Related

- [API_REFERENCE.md](API_REFERENCE.md) — full request/response shapes for the `/internal/apps/*` endpoints
- [CONFIGURATION.md](CONFIGURATION.md) — env-var reference
