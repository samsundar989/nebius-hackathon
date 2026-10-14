# Feedback on Nebius and NVIDIA tools (mandatory submission section)

For each tool: what we used it for · what worked · what needs work · zero-to-hello-world onboarding experience (minutes, blockers, exact error strings) · would we build with it again. Be specific and measured; this is read by the PMs/DevRel who own these products.

## Nebius Token Factory (inference API)
Measured 2026-10-14 with `scripts/smoke_tf.py` (raw output in `runs/smoke_tf_*.json`, not committed; capabilities distilled into `leakproof/llm/tf_capabilities.json`). 62 calls, total **$0.0089**.
- Used for: every model call in Leakproof (planner, workers, triage) through the plain `openai` SDK with `base_url=https://api.tokenfactory.nebius.com/v1/`.
- Worked:
  - OpenAI compatibility is real: `chat.completions`, `tools`, `response_format`, `with_raw_response` headers all worked unchanged. `GET /v1/models` 200 in 0.42 s, 25 models, all four Nemotron IDs present.
  - Both thinking switches pass through: `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` and top-level `reasoning_effort="none"` each took Ultra and Lightning to 0 reasoning tokens.
  - Rate limits are far higher than the ~60 RPM folklore: headers say `x-ratelimit-limit-requests: 600`, `x-ratelimit-limit-tokens: 400000`, plus `x-ratelimit-dynamic-scale-*`, `x-ratelimit-dynamic-period-remaining: 872s`, `x-ratelimit-dynamic-period-usage-*`. 20 concurrent Lightning calls: 20/20 OK, no 429, wall 3.1 s, p50 1.7 s, max 3.1 s.
  - Parallel tool calls on chat completions: all four Nemotron models returned both tools (`get_weather` + `get_local_time`) in one turn with `parallel_tool_calls=true`, latency 0.4–0.6 s.
  - `usage.completion_tokens_details.reasoning_tokens` is populated (Ultra, Lightning, Super) and is a subset of `completion_tokens` (OpenAI convention), so local cost computation is straightforward.
- Needs work:
  - **Batch API unavailable:** `POST /v1/batches` → `HTTP 403: {'detail': 'Creating new batch job is temporarily unavailable'}` (file upload with `purpose="batch"` succeeded first). No docs mention this state or an ETA.
  - **`response_format: json_schema` + numeric fields runs away.** The schema *is* enforced (the model used key names that appear only in the schema), but number/integer fields are decoded digit-by-digit until `max_tokens`: Lightning 4/4 probes (`number` strict and non-strict, `integer`, `number` with `multipleOf: 0.1`) ended `finish_reason=length` with output like `"zq_population_millions": 68.3964561082864470000000…`; Ultra 1/5 (`68.478133504704…`), and once returned `683734332024` for an `integer` "millions" field. Same request with the schema only in the prompt and thinking on: clean `68.4` on both. Workaround in our client: treat `finish_reason=length` as failure and fall back to prompt-embedded schema + validation.
  - `reasoning_effort` levels are not honored on Ultra/Lightning: low vs high gave 185 vs 166 (Ultra) and 384 vs 353 (Lightning) reasoning tokens on the same prompt; only Super responds (28 vs 92). Only `none` matters there.
  - Reasoning lives in different fields per model: `message.reasoning_content` (Ultra, Lightning, Super) vs `message.reasoning` (Nano). Nano also reports `reasoning_tokens: 0` while returning reasoning text, so its reasoning cost is invisible in usage details (still inside `completion_tokens`).
  - No spend cap and no cost field in the response; we compute $ locally from the price list.
  - Sandboxes `whoami` and Token Factory share the key but Sandboxes need a `Project:` header with the `aiproject-…` id, while the AI Cloud console/CLI uses a `project-…` id — the docs call both "project ID".
- Zero-to-hello-world: < 5 minutes once the key existed (models list + first chat). Discovering the thinking switch, json_schema behavior and the batch 403 took a 57-second scripted probe plus one follow-up; none of it is on the model cards.
- Build again?: Yes — the OpenAI-compatible surface and generous rate limits made a thin client enough.

## Nemotron 3 Ultra
`nvidia/Nemotron-3-Ultra-550b-a55b` — planner/root-cause. Hello 1.5 s; reasoning on by default (181 reasoning tokens for a two-step probability question, 0.98 s, correct `5/14`). Thinking off: 5 tokens, 0.37 s, still correct via `chat_template_kwargs`, but **wrong (`2/7`) via `reasoning_effort=none`** on the same prompt — thinking-off answers are not reliable for reasoning. json_schema numeric runaway 1/5. Tool calls fine.

## Nemotron 3.5 Lightning
`nvidia/Nemotron-3_5-Lightning` — patch worker. Verbose thinker: **846 reasoning tokens for "Say hello in five words."** (3.0 s). Reasoning question: 345 reasoning tokens, 1.3 s, correct; thinking off: 0.26 s but **wrong both ways (`5/28`, `8/14`)**. Implication for workers: keep thinking on for patch reasoning, off only for mechanical formatting. json_schema numeric fields run away 4/4. 20-way concurrency clean.

## Nemotron 3 Nano
`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` — triage. Reasoning in `message.reasoning` (not `reasoning_content`), `reasoning_tokens` always reported 0. `chat_template_kwargs` off works (but answered `5/12`, wrong); `reasoning_effort=none` returned **empty content** with 4 chars of reasoning — use `chat_template_kwargs` for Nano. json_schema worked cleanly (45 tokens, valid).

## Nemotron 3 Super
`nvidia/nemotron-3-super-120b-a12b` — alternate planner. Was `status: error` in the catalog on 2026-10-13; **up on 2026-10-14**. With thinking off it writes its chain of thought into `content` (141 tokens of "The total number of ways…") instead of answering, so "off" saves no tokens there. The only model where `reasoning_effort` low/high changes anything (28 vs 92 reasoning tokens). json_schema clean (27 tokens).

## Token Factory Sandboxes (Contree)
- Used for: planned as the branch-per-hypothesis runner (`leakproof/runner/contree.py`, contree-sdk 0.3.6). Not yet usable: access pending.
- Worked: `GET /sandboxes/v1/whoami` answers in ~0.46 s and returns useful limits: `instance_max_timeout: 3600`, `instance_max_concurrency: 50`, `instance_max_layer_bytes: 12884901888` (12 GiB), `images_import_max_concurrency: 8`, `images_import_max_timeout: 3600`. The SDK source is readable and typed, so the request model could be verified without access.
- Needs work:
  - **"Not approved" is a 200, not a 403.** An unapproved project gets `200` with `permissions: {import: false, spawn: false, spawn_disposable: false, list: false, cancel: false, set_image_tag: false}`. The docs and community advice say to expect 403, so a naive "200 = approved" check is wrong. The same body came back for both of our project-ID formats.
  - **No networking switch in contree-sdk 0.3.6.** `InstanceSpawnRequest` has no networking field and `ImageLike.run()` has no `network` argument, although the docs describe `networking.enabled=false`. An offline verification step can't be expressed through the pinned SDK. Our runner refuses (`UnsupportedOption`) rather than silently run with a NIC.
  - No Dockerfile build in the SDK. We replay FROM/RUN/ENV/WORKDIR/COPY as chained saved runs (untested until access lands). Image `ENV` with `${PATH}` references has to be exported inside the guest shell.
  - Project-ID confusion: the `Project:` header takes the Token Factory `aiproject-…` id; the AI Cloud console uses `project-…` ids; the docs call both "project ID", and the contree CLI env var `NEBIUS_AI_PROJECT` suggests the AI Cloud one.
- Zero-to-hello-world: blocked on beta approval (requested 2026-10-13).
- Build again?: TBD after access.

## Token Factory Batch API

## Nebius AI Cloud — Serverless Jobs

## Nebius CLI

## NVIDIA compute-sanitizer (and ncu/nsys where attempted)
- Used for: the CUDA arm of the gate (memcheck for out-of-bounds, `--leak-check full` for `cudaMalloc` leaks). Two injected-defect samples in `cases/cuda/`, run by `cases/cuda/run_samples.sh`.
- Worked: on a Kaggle Tesla T4 (sm_75, driver 580.178.04, CUDA 12.8, Compute Sanitizer 2025.1.0), both defects were found on the first try. Memcheck reported `Invalid __global__ write of size 4 bytes ... in oob_global.cu:8 ... by thread (255,0,0) in block (3,0,0)` with the exact source line, and "1 bytes after the nearest allocation ... of size 4,096 bytes". Leak-check reported `Leaked 4,096 bytes` with a host allocation stack down to `make_buffer(int) in leak_cudamalloc.cu:12`. The whole Kaggle run, push to output, took 45 s.
- Needs work:
  - **The exit code is 0 for both defects** unless `--error-exitcode` is passed. A gate that trusts the exit code would pass every buggy CUDA program, so we parse the report.
  - **It does not run on the local RTX 5090 under WSL2.** `nvidia/cuda:12.6.3-devel` with `--gpus all` printed `Error: Failed to initialize WDDM debugger interface. Please run EnableDebuggerInterface.bat as an administrator` and `Error: Device not supported. Please refer to the "Supported Devices" section of the sanitizer documentation`. The kernel then ran uninstrumented: `kernel: no error`, and the leak sample reported `LEAK SUMMARY: 0 bytes leaked in 0 allocations`. A tool that cannot attach produces a report that looks clean. We detect those lines (`compute_sanitizer_tool_errors`) and treat the run as inconclusive.
  - Output format drifts between releases. 2025.1 prints thousands separators (`4,096`) and host frames as `func in file:line [pc] in module`; our first parser, written from older docs, missed both.
  - ncu: `ERR_NVGPUCTRPERM` on Kaggle (no performance-counter permission); on WSL2: `Failed to load Nsight Compute CUDA modules`. Not needed for the gate.
- Zero-to-hello-world: about 10 min on Kaggle (a private script kernel; the sanitizer ships in `/usr/local/cuda`). Locally it was not reached: a CUDA image (11.5 GB), then the two errors above.
- Would build again: yes, on native Linux GPUs (Kaggle, L40S). Not on WSL2 without the debugger interface and a CUDA ≥ 12.8 image.

## Tavily (if used)

## Docs and onboarding (cross-cutting)
- Thinking control, reasoning-field names, json_schema behaviour and the batch outage are all learnable only by probing. One "Nemotron on Token Factory" page covering request knobs (`chat_template_kwargs` vs `reasoning_effort`, which models honour effort levels, where reasoning text lands, whether `reasoning_tokens` is reported) would have saved most of our first hour.
