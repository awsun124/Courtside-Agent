# Investigating stories

The investigator uses a bounded loop of read-only tools after the deterministic
ranking step. It does not change scores, merge clusters, or mark developments as
reviewed. Each candidate keeps its investigation activity, evidence references,
source excerpts, uncertainty notes, and previous-briefing comparison.

## Run without an LLM

Manual API refreshes run the investigator automatically. The default provider
is `rules`, which needs no key or network access beyond the news collection.
It is a deterministic investigation workflow, not an AI-generated analysis.

To investigate an already saved briefing without refreshing news:

```sh
python -m courtside.investigate
python -m courtside.investigate --mode sample
```

The command reads the latest saved briefing and its processing snapshot. It
writes `artifacts/investigation/investigation.md` and `investigation.json` without
changing the saved briefing. API refreshes save investigation results in SQLite.

## Tools and decisions

The investigator can:

- `search_articles`: search saved titles and descriptions, excluding filtered promotions.
- `retrieve_material`: retrieve saved API excerpts by article ID.
- `inspect_related_stories`: inspect related names or teams without assuming the same event.
- `compare_previous_briefings`: compare links, publisher-group counts, and scores with up to three previous briefings.
- `finish`: submit exact source excerpts with evidence IDs.

The rules provider inspects related groups, compares previous briefings, searches
for coverage, and chooses excerpts to retrieve. It prioritizes different reporting
groups, then checks other matching evidence if space remains. A single-source
story therefore gets a different evidence trail from a broader story. Related
coverage may describe another event and is not automatically merged or cited as
evidence for the target story.

Full publisher pages are not fetched. Retrieval uses only the article metadata
and excerpts already returned by the news API. There is no arbitrary URL tool,
shell, file access, or new web search inside the investigator.

## Evidence and summaries

Every summary quote must appear exactly in a retrieved title, description, or
excerpt from the target story. Unknown references, unretrieved material, outside
stories, and unsupported paraphrases are rejected. A missing summary is allowed
when evidence is insufficient.

Summaries have `kind: source_excerpts` and attribute each excerpt to its publisher
with a link and publication date. They are not independent fact verification.
Likely copies still count as one reporting group when describing corroboration.
Rumor wording stays labeled as unconfirmed. No private chain-of-thought is
requested, saved, or returned. Activity contains tool names, validated arguments,
evidence IDs, and concise summaries of completed actions.

All external material is untrusted. Obvious instruction-like content is quarantined
and cannot be quoted. That check is a precaution, not a complete injection
detector. The stronger boundary is that the tools cannot access credentials,
execute commands, browse outside the saved collection, or change ranking data.

Previous-briefing comparisons match story IDs or overlapping source URLs.
They report new and removed links and score changes. New links alone do not
establish a substantive development, so `meaningful_update` remains
`not established`. Distinct articles with no shared IDs or links can still
describe the same event. Full event matching and substantive-update review
remain limitations of this version.

## Limits

`config/investigation.json` sets:

- Up to ten story candidates per briefing.
- Eight steps per story and 80 steps across the briefing.
- Fifteen seconds across the briefing, checked between actions.
- Six retrieved article IDs per story.
- Three LLM request attempts across the briefing, when explicitly enabled.
- At most 16,000 input characters per LLM request and 1,000 completion tokens.

Provider requests use the remaining time as a curl timeout. Calls are not retried
automatically. A loop that reaches a limit keeps its evidence trail and is labeled
partial. It does not pretend to have finished an investigation. Actual HTTP call
counts and provider-attempt counts are recorded separately when available.

The source refresh still has its own request and time limits. The API reserves a
longer refresh lease to cover collection plus investigation. Optional investigation
failure leaves numerical ranking available with an unavailable status.

## Optional LLM provider

There is a small adapter for providers supporting the OpenAI Chat Completions
tool-calling format. It has only been tested with mocked responses, not a live
paid model. It requires both an explicit provider choice and a server-side opt-in.
Do not enable it until API spending and source-processing permissions are approved.

In `config/investigation.json`, set `provider` to `openai-compatible`. Then configure
these local environment values using `.env.example` as a template:

```dotenv
ENABLE_LLM_CALLS=false
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=
LLM_API_KEY=
```

Calls remain disabled while `ENABLE_LLM_CALLS` is false. Enabling them also needs
a model that supports tool calling and a separate LLM API key. The GNews key is
never used as an LLM key. HTTPS is required except for a localhost provider.
Credentials go through curl's standard input, not process arguments or logs.
There are no redirects, dynamic provider URLs, or tools supplied by article text.

The adapter accepts one native tool call per response. It ignores assistant prose
and reasoning fields. Only validated tool calls enter the loop, and only retrieved
quotes can enter a final summary. Compatibility with other providers depends on
their support for this tool schema and `max_completion_tokens`.

References: [function calling](https://developers.openai.com/api/docs/guides/function-calling)
and [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).


## Feed restrictions

Feed-only material is excluded before investigation starts. A cluster containing restricted material keeps its deterministic score and source links but receives no generated summary or investigation. Restricted articles and previous candidate contexts are withheld from provider inputs. See [feed collection](feeds.md).

## One small agent check

Run `python -m scripts.check_agent` for an offline check using fictional injury
reports and a separate trade rumor about the same fictional player. It checks
related-story inspection, search, retrieval, in-story citations, and unchanged
scores. Results go to ignored `artifacts/agent-check/report.json`.

`python -m scripts.check_agent --live` runs the same case with the configured LLM.
It requires the existing server-side key, model, and explicit opt-in. It permits
at most five API attempts, eight steps, 20 seconds, 16,000 input characters per
request, and 500 output tokens per request. It does not change the app's settings.
A blocked or incomplete run fails visibly and does not fall back to rules.
The offline baseline passes. The live LLM check has not been run or funded.
This evaluates evidence boundaries, not independent reasoning or news accuracy.
