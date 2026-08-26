# Task 1: Anthropic (Claude) provider for the Moodle core AI subsystem — survey, then plan

## Context

Oivus is a Moodle-based homeschooling environment. We intend to use the Moodle
core AI subsystem (introduced in 4.5, extended through 5.2) as the abstraction
layer for all LLM functionality, so that the eventual grading features (see
Task 2) remain provider-agnostic. The immediately required backend is
Anthropic Claude via the Anthropic Messages API.

First determine the Moodle version targeted by this repo (check `version.php`
/ composer / docs in the repo) and pin all findings and plans to that version's
AI subsystem API, noting any differences against 4.5 LTS and 5.2.

## Phase A — Survey (do this first; it may make Phase B unnecessary)

Establish whether a usable native Anthropic `aiprovider_*` plugin already
exists. Check, at minimum:

1. Moodle plugins directory (moodle.org/plugins) and the new Moodle
   Marketplace (marketplace.moodle.com) — search: anthropic, claude,
   aiprovider.
2. GitHub / GitLab code search: `aiprovider_anthropic`, `aiprovider_claude`,
   `moodle anthropic provider`.
3. The provider list shipped in core for the target Moodle version. Note that
   Moodle 5.2 core includes an **Amazon Bedrock** provider, and Bedrock serves
   Claude models — evaluate this as a zero-code fallback route and record its
   trade-offs (AWS account, region/data-residency for Finland/EU, pricing,
   model availability and lag behind Anthropic's own API).
4. Whether any generic "OpenAI-compatible endpoint" provider exists that could
   be pointed at Anthropic's OpenAI-compatibility layer
   (https://docs.anthropic.com/ — check current status of the compatibility
   endpoint). Record this as a fallback only; native Messages API support is
   preferred (system prompt handling, max_tokens semantics, streaming, and
   future tool use differ).

For each candidate found, record: maintainer, licence, supported Moodle
versions, supported AI actions (`generate_text` at minimum), maintenance
activity, and whether it uses the Messages API properly (system prompt as
top-level `system` field, correct token accounting).

**Decision gate:** if a maintained, GPL-compatible, native provider exists
covering `generate_text` for our Moodle version → write a short report
recommending it (with any needed patches) and STOP. Otherwise proceed to
Phase B.

## Phase B — Plan (plan only; no implementation in this task)

Produce `docs/plans/aiprovider_anthropic-plan.md` covering:

1. **Plugin skeleton.** Frankenstyle `aiprovider_anthropic`. Enumerate the
   classes the target Moodle version requires (e.g. provider class extending
   `\core_ai\provider`, per-action processor classes such as
   `process_generate_text`, settings/admin form, lang strings, `version.php`,
   privacy provider). Base the enumeration on an existing core provider
   (OpenAI or Ollama) in the target version's source tree — read the actual
   code, do not rely on memory of the API.
2. **Actions.** Support `generate_text` fully. State explicitly which actions
   are declared unsupported (`generate_image`, `summarise_text` /
   `explain_text` — note: in core these text actions may be routed through
   generate-style processing; verify in source and document).
3. **API mapping.** Messages API request construction: model selection
   (admin-configurable, default to a current Claude model; do not hardcode a
   soon-to-expire model name without a settings override), `system` prompt
   passthrough from the subsystem's global/system prompt mechanism,
   `max_tokens`, temperature, timeout, retry policy on 429/529 with backoff.
   Non-streaming first; note whether the subsystem's action interface in the
   target version supports streaming at all.
4. **Error handling.** Map Anthropic error classes to the subsystem's error
   reporting so failures surface sensibly in the UI and logs.
5. **Configuration & governance.** API key storage (admin setting, never in
   course context), rate limiting hooks if the subsystem provides them,
   per-model cost note in settings help.
6. **Privacy.** Privacy API declaration: what is sent off-site (submitted
   text, prompts), retention statement, GDPR note for EU deployment.
7. **Testing.** PHPUnit with mocked HTTP (use Moodle's `curl` mocking or
   Guzzle mock handler as the version dictates); one optional live smoke test
   gated behind an env var.
8. **Effort estimate and file-by-file work breakdown.**

## Constraints

- GPL v3 (Moodle plugin requirement).
- No secrets in the repo; API key via admin settings only.
- Match Moodle coding style (moodle-cs / codechecker clean).

## Deliverables

- Phase A: `docs/reports/aiprovider-survey.md` with findings and a
  recommendation.
- Phase B (only if needed): `docs/plans/aiprovider_anthropic-plan.md`.
