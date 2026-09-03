# Survey: Anthropic (Claude) provider for the Moodle AI subsystem

Survey date: 2026-08-26. Decision gate for adopting an Anthropic provider
rather than writing one; the outcome is summarised in
[`LESSONS-LEARNED.md`](LESSONS-LEARNED.md).

## Target Moodle version

`versions.yml` pins `moodle-5.1.6` (stable501 tarball). All findings below are
pinned to the Moodle 5.1 AI subsystem.

Core AI providers per version (verified from the moodle/moodle source tree):

| Branch | Core providers under `public/ai/provider/` |
|---|---|
| 5.1 (`MOODLE_501_STABLE`) | `azureai`, `deepseek`, `ollama`, `openai` |
| 5.2 (`MOODLE_502_STABLE`) | adds `awsbedrock`, `gemini` |

No Anthropic provider in core on any branch. The brief's note that the Bedrock
provider is core only from 5.2 is confirmed; on 5.1 Bedrock requires the
contributed plugin (below).

Relevant subsystem differences: 4.5 LTS uses the older single-instance
provider configuration; the provider-instance model (per-instance action
config, `after_ai_provider_form_hook` / `after_ai_action_settings_form_hook`)
is the 5.x shape, which is why the leading candidates require ≥ 5.0.
`\core_ai\error\factory` exists in 5.1 (candidates guard it with
`class_exists` only for pre-5.0 tolerance).

## Candidates found

### 1. `aiprovider_claude` — Claude API Provider (recommended)

- Directory: <https://moodle.org/plugins/aiprovider_claude> (redirects to
  <https://marketplace.moodle.com/plugins/aiprovider_claude>)
- Source: <https://github.com/ashishptl21/moodle-aiprovider_claude>
- Maintainers: Ashish Patel, Raju Patel (Treesha Infotech)
- Licence: GPL v3 or later
- Latest release: 1.0.4 (2026082500), released 2026-08-25 — the day before
  this survey
- Moodle support: `requires` 2025041400 (5.0), `supported [500, 502]` →
  covers 5.0–5.2, so 5.1.6 is in range. Marketplace page claims 4.5–5.2;
  `version.php` is authoritative: **5.0 minimum**.
- Adoption: 279 installs, ~350 downloads/90 days. Marketplace badges:
  automated testing, privacy friendly, early-bird 5.2.
- Actions: `generate_text`, `summarise_text`, `explain_text`
  (summarise/explain subclass `process_generate_text` — same Messages API
  pipeline). No `generate_image` (Anthropic has no image-generation API).

Code review (cloned, tag 1.0.4):

- **Messages API used properly.** `POST /v1/messages` with top-level `system`
  field for the system instruction; `x-api-key` auth;
  `anthropic-version` header admin-configurable (default `2023-06-01`);
  `metadata.user_id` set from Moodle's anonymised per-user hash.
- **Token accounting correct.** Reads `usage.input_tokens` /
  `usage.output_tokens` into `prompttokens` / `completiontokens`; also
  returns `stop_reason` and the response `model`.
- **Error handling.** Non-2xx mapped through `\core_ai\error\factory`
  (subsystem-native error surfacing); 5xx falls back to the reason phrase.
- **Model catalogue current.** Hardcoded list updated 2026-08-25: Opus 5,
  Fable 5, Opus 4.8/4.7/4.6, Sonnet 4.6/4.5, Haiku 4.5, plus a
  free-form "custom" model with extra-parameter passthrough (JSON), so new
  model IDs never block. Temperature is correctly withheld for the models
  that no longer accept it (Fable 5, Opus 5, Opus 4.8/4.7).
- **Rate limiting.** Uses the core per-user/global rate limiters; both paths
  covered by unit tests.
- **Tests.** 15 PHPUnit test methods incl. request construction, success and
  error handling, and rate limiters, with fixture-based mocked HTTP.
- **Privacy API.** Declares external location link (prompt text, model sent
  off-site); null-provider pattern for stored data (nothing stored locally).
  Minor blemish: the metadata list mentions `numberimages`/`responseformat`,
  copied from the OpenAI provider — irrelevant fields, cosmetic only.
- Maintenance history: 6 commits, Mar–Aug 2026; releases track Anthropic
  model launches (Apr, Jul, Aug 2026). Small but responsive.

Gaps (candidate patches, none blocking):

- No retry/backoff on 429/529; a failed call surfaces as an error. Acceptable
  for single-user drilling; patch upstream if it bites.
- `max_tokens` defaults to the model maximum (e.g. 128 000) — set a sane
  per-action value (e.g. 1000–4000) in the instance config instead.
- Model list is hardcoded (no `/v1/models` discovery), mitigated by the
  custom-model option.

### 2. `aiprovider_anthropic` — Anthropic API Provider (runner-up)

- Directory: <https://marketplace.moodle.com/plugins/aiprovider_anthropic>
- Source: <https://github.com/LucaDR1998/moodle-aiprovider_anthropic>
- Maintainer: Luca Demicheli Rubio (single individual)
- Licence: GPL v3 or later; release 1.0.0 (stable), `requires` 2025100600
  (Moodle 5.1); marketplace lists 4.5–5.1
- Actions: generate/summarise/explain; dynamic model discovery via the
  Anthropic models endpoint with caching and fallback
- Adoption: 17 installs; last release ~2026-03; last push 2026-03-30

Technically credible (nice model-discovery feature) but five months idle,
single maintainer, ~17 sites. Higher continuity risk than candidate 1.

### 3. `blindsidenetworks-ps/moodle-aiprovider_anthropic` (GitHub only)

0.1.0-alpha.1, `requires` 2026041000 (≈ 5.2), not in the plugins directory,
0 stars. Not a candidate for 5.1.

## Fallback routes (recorded, not needed)

### Amazon Bedrock

- On Moodle 5.1 core has no Bedrock provider; the contributed
  `aiprovider_bedrock` (Meeple srl, GPL v3+, supports 4.5+,
  <https://github.com/meeplesrl/moodle-aiprovider_bedrock>, 31 installs)
  serves Claude models via AWS.
- Trade-offs: requires an AWS account, IAM keys and Bedrock model-access
  grants; EU regions available (eu inference profiles), so Finnish/EU data
  residency is satisfiable, but it adds a second cloud vendor and AWS
  billing; Bedrock's Claude catalogue lags Anthropic's own API (plugin
  tested up to Sonnet 4.6; no Opus 5/Fable 5 parity at survey time);
  pricing ≈ Anthropic list price plus AWS peculiarities.
- Verdict: strictly worse than a native provider for this deployment; only
  interesting if an AWS estate already existed.

### OpenAI-compatibility layer

- Anthropic exposes an OpenAI-compatible `/v1/chat/completions` endpoint
  (base URL `https://api.anthropic.com/v1/`). Anthropic's docs state it is
  "primarily intended to test and compare model capabilities, and is not
  considered a long-term or production-ready solution". System messages are
  hoisted and concatenated; several fields silently ignored; no prompt
  caching.
- A generic `aiprovider_openaicompatible` plugin exists (ADORSYS-GIS,
  supports 5.0–5.2) and could be pointed at it.
- Verdict: fallback only, as the brief anticipated; with a good native
  provider available there is no reason to take the compatibility-layer
  risk.

## Decision gate

**A maintained, GPL-compatible, native provider covering `generate_text` for
Moodle 5.1 exists: `aiprovider_claude` 1.0.4.** Code inspection confirms
proper Messages API usage (top-level `system`, correct token accounting),
subsystem-native error handling, rate limiting, tests, and a current model
catalogue.

**Recommendation:** adopt `aiprovider_claude`, pinned per repo convention
(GitHub tag `1.0.4` + sha256, installed into `ai/provider/claude` in the
image build, like the STACK plugins). Configure per-action `max_tokens`
explicitly; consider contributing 429/529 backoff upstream if needed.

**Phase B is not required.** No `aiprovider_anthropic` plan will be written.
