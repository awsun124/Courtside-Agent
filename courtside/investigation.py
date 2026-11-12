from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import time

from scripts.validate_gdelt import canonical_url
from .stories import clean_text


@dataclass
class InvestigationSettings:
    provider: str = "rules"
    max_stories: int = 10
    max_steps: int = 80
    max_steps_per_story: int = 8
    max_seconds: float = 15
    max_articles_per_story: int = 6
    max_llm_calls: int = 3
    max_input_characters: int = 16000
    max_output_tokens: int = 1000

    def validate(self):
        if self.provider not in {"rules", "openai-compatible"}:
            raise ValueError("Unknown investigation provider")
        limits = {"max_stories": 10, "max_steps": 100, "max_steps_per_story": 12,
                  "max_articles_per_story": 8, "max_llm_calls": 5,
                  "max_input_characters": 32000, "max_output_tokens": 2000}
        for name, maximum in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}")
        if type(self.max_seconds) not in (float, int) or not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 30:
            raise ValueError("Investigation time must be positive and no more than 30 seconds")


def evidence_id(url):
    return "article-" + hashlib.sha256(canonical_url(url).encode()).hexdigest()[:16]


def short_text(text, limit=1200):
    return " ".join((text or "").split())[:limit]


def suspicious_text(text):
    text = clean_text(text)
    return any(phrase in text for phrase in ["ignore previous instructions", "ignore all instructions",
                "system prompt", "reveal your", "api key", "execute this", "run shell", "call this tool"])


class EvidenceTools:
    def __init__(self, result, briefing, previous):
        self.articles = {evidence_id(article["url"]): article for article in result["articles"]}
        self.groups = {story["id"]: story for story in result["stories"]}
        self.candidates = {story["id"]: story for story in briefing["candidates"]}
        self.previous = previous
        self.mode = briefing.get("data_mode", "live")

    def article_ids(self, story_id):
        return [evidence_id(url) for url in self.groups[story_id]["article_urls"]]

    def article_label(self, article_id):
        article = self.articles[article_id]
        return dict(evidence_id=article_id, title=short_text(article["title"], 200),
                    publisher=article["publisher_name"], url=article["url"],
                    published_at=article["published_at"], untrusted=True)

    def search_articles(self, query, limit):
        if not isinstance(query, str) or not 1 <= len(query) <= 200 or type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError("Search needs a short query and a limit from 1 to 5")
        words = set(clean_text(query).split())
        matches = []
        for article_id, article in self.articles.items():
            if article.get("decision") == "excluded" or article.get("investigation_allowed") is False:
                continue
            text = clean_text(article["title"] + " " + (article.get("description") or ""))
            overlap = len(words & set(text.split()))
            if overlap:
                matches.append((overlap, article_id))
        matches.sort(key=lambda item: (-item[0], item[1]))
        return dict(matches=[self.article_label(article_id) for _, article_id in matches[:limit]],
                    scope="Saved article metadata only")

    def retrieve_material(self, article_id):
        if article_id not in self.articles:
            raise ValueError("Evidence must refer to a collected article ID")
        article = self.articles[article_id]
        if article.get("decision") == "excluded":
            raise ValueError("Excluded articles are not available as reporting evidence")
        if article.get("investigation_allowed") is False:
            raise ValueError("This source is available as a headline and link only")
        texts = {name: short_text(article.get(field)) for name, field in
                 [("title", "title"), ("description", "description"), ("excerpt", "content_excerpt")]}
        quarantined = suspicious_text(" ".join(texts.values()))
        return dict(**self.article_label(article_id), material_scope="Saved API excerpt, not full article text",
                    material={} if quarantined else texts, quarantined=quarantined)

    def inspect_related_stories(self, story_id):
        if story_id not in self.groups:
            raise ValueError("Unknown story ID")
        target = self.groups[story_id]
        target_features = [self.articles[evidence_id(url)].get("features", {}) for url in target["article_urls"]]
        teams = {team for features in target_features for team in features.get("teams", [])}
        people = {person for features in target_features for person in features.get("people", [])}
        related = []
        for other in self.groups.values():
            if other["id"] == story_id:
                continue
            features = [self.articles[evidence_id(url)].get("features", {}) for url in other["article_urls"]]
            if any(teams & set(item.get("teams", [])) or people & set(item.get("people", [])) for item in features):
                related.append(dict(story_id=other["id"], title=short_text(other["title"], 200),
                                    event=other["event"], evidence_ids=self.article_ids(other["id"]),
                                    relation="Shared names or teams, not necessarily the same event"))
        return dict(story_id=story_id, event=target["event"], evidence_ids=self.article_ids(story_id),
                    related=related[:5])

    def compare_previous_briefings(self, story_id):
        if story_id not in self.candidates:
            raise ValueError("Unknown story ID")
        current = self.candidates[story_id]
        urls = {canonical_url(url) for url in current["evidence_urls"]}
        for briefing in self.previous[:3]:
            if briefing.get("data_mode", "live") != self.mode:
                continue
            for old in briefing["candidates"]:
                old_urls = {canonical_url(url) for url in old["evidence_urls"]}
                if old["id"] != story_id and not urls & old_urls:
                    continue
                return dict(status="compared", previous_briefing_id=briefing.get("briefing_id"),
                            previous_as_of=briefing["as_of"], new_source_urls=sorted(urls - old_urls),
                            removed_source_urls=sorted(old_urls - urls),
                            publisher_group_change=current["breakdown"]["coverage"]["independent_publishers"] - old["breakdown"]["coverage"]["independent_publishers"],
                            score_change=current["score"] - old["score"], meaningful_update="not established",
                            note="New links or scores alone do not establish a substantive development")
        return dict(status="no_previous_match", meaningful_update="not established",
                    note="No matching story found in the last three saved briefings. This does not prove the event is new.")

    def call(self, name, arguments):
        allowed = {"search_articles": {"query", "limit"}, "retrieve_material": {"article_id"},
                   "inspect_related_stories": {"story_id"}, "compare_previous_briefings": {"story_id"}}
        if name not in allowed or not isinstance(arguments, dict) or set(arguments) != allowed[name]:
            raise ValueError("Unknown tool or unsupported arguments")
        return getattr(self, name)(**arguments)


def source_excerpt(text, limit=240):
    sentences = [match.end() for match in re.finditer(r'[.!?]["’”\']?(?=\s|$)', text[:limit + 1]) if match.end() <= limit]
    if sentences:
        return text[:sentences[-1]].strip()
    if len(text) <= limit:
        return text.strip()
    cutoff = text.rfind(" ", 0, limit + 1)
    return text[:cutoff if cutoff > 0 else limit].rstrip()


class RulesProvider:
    name = "rules"
    uses_llm = False

    def start(self, context):
        pass

    def choose(self, state, timeout):
        story_id = state["story_id"]
        for tool in ["inspect_related_stories", "compare_previous_briefings"]:
            if tool not in state["results"]:
                return dict(name=tool, arguments=dict(story_id=story_id))
        if "search_articles" not in state["results"]:
            return dict(name="search_articles", arguments=dict(query=state["query"], limit=5))
        remaining = state["priority_ids"] + [item["evidence_id"] for item in state["results"]["search_articles"]["matches"]]
        if state["steps_left"] > 1 and len(state["retrieved"]) < state["article_limit"]:
            for article_id in remaining:
                if article_id not in state["retrieved"]:
                    return dict(name="retrieve_material", arguments=dict(article_id=article_id))
        claims = []
        for article_id in state["summary_ids"]:
            material = state["retrieved"].get(article_id)
            if material and not material["quarantined"]:
                text = material["material"].get("description") or material["material"].get("title")
                if text:
                    claims.append(dict(evidence_id=article_id, quote=source_excerpt(text)))
            if len(claims) == 2:
                break
        return dict(name="finish", arguments=dict(claims=claims))

    def observe(self, action, result):
        pass


def supported_summary(claims, retrieved, allowed_ids):
    if not isinstance(claims, list) or len(claims) > 3:
        raise ValueError("A summary can contain at most three evidence excerpts")
    citations, lines = [], []
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"evidence_id", "quote"}:
            raise ValueError("Summary claims must contain only an evidence ID and quote")
        article_id, quote = claim["evidence_id"], claim["quote"]
        material = retrieved.get(article_id)
        if (article_id not in allowed_ids or material is None or material["quarantined"] or
                not isinstance(quote, str) or not 5 <= len(quote) <= 300 or
                not any(quote in text for text in material["material"].values())):
            raise ValueError("Summary text must come from retrieved, in-story evidence")
        ending = "" if re.search(r'[.!?…]["’”\']?$', quote) else "…"
        lines.append(f"{material['publisher']} reports: {quote}{ending}")
        citations.append(dict(evidence_id=article_id, url=material["url"], publisher=material["publisher"],
                              quote=quote, published_at=material["published_at"]))
    if not citations:
        return None
    return dict(kind="source_excerpts", text="\n".join(lines), citations=citations,
                note="Attributed API excerpts, not independently verified facts")


def investigate_briefing(result, briefing, previous=None, settings=None, provider=None, clock=time.monotonic):
    settings = settings or InvestigationSettings()
    settings.validate()
    if provider is None:
        if settings.provider != "rules":
            raise ValueError("The configured LLM provider has not been enabled")
        provider = RulesProvider()
    tools = EvidenceTools(result, briefing, previous or [])
    started_at = clock()
    deadline, steps, llm_calls = started_at + settings.max_seconds, 0, 0
    records = {}
    for position, candidate in enumerate(briefing["candidates"]):
        story_id = candidate["id"]
        record = dict(provider=provider.name, status="limited", summary=None, activity=[], evidence_references=[],
                      what_changed=None, uncertainty=["Investigation limits reached before this story was completed"],
                      corroboration=dict(retrieved_reporting_groups=0, status="not_checked"),
                      decision_summary="Investigation limits reached before this story was completed")
        records[story_id] = record
        if position >= settings.max_stories or steps >= settings.max_steps or clock() >= deadline:
            continue
        target_ids = tools.article_ids(story_id)
        primary_ids = [evidence_id(group["evidence_urls"][0]) for group in candidate["reporting_groups"]]
        priority = list(dict.fromkeys(primary_ids + target_ids))
        first = tools.articles[target_ids[0]] if target_ids else {}
        query = " ".join(first.get("features", {}).get("people", [])) or short_text(candidate["title"], 200)
        state = dict(story_id=story_id, query=query, priority_ids=priority, summary_ids=primary_ids, results={}, retrieved={},
                     article_limit=settings.max_articles_per_story, steps_left=settings.max_steps_per_story)
        provider.start(dict(story_id=story_id, title=short_text(candidate["title"], 200), evidence_ids=target_ids,
                            data_mode=tools.mode, untrusted=True))
        for story_step in range(settings.max_steps_per_story):
            if steps >= settings.max_steps or clock() >= deadline:
                break
            if provider.uses_llm:
                if llm_calls >= settings.max_llm_calls:
                    break
                llm_calls += 1
            state["steps_left"] = min(settings.max_steps_per_story - story_step, settings.max_steps - steps)
            state["calls_left"] = settings.max_llm_calls - llm_calls + 1 if provider.uses_llm else None
            try:
                action = provider.choose(state, max(0.01, deadline - clock()))
                if clock() >= deadline:
                    break
                steps += 1
                name, arguments = action["name"], action["arguments"]
                if name == "finish":
                    if not isinstance(arguments, dict) or set(arguments) != {"claims"}:
                        raise ValueError("Finish accepts only cited excerpts")
                    record["summary"] = supported_summary(arguments["claims"], state["retrieved"], set(target_ids))
                    record["status"] = "complete" if record["summary"] else "insufficient_evidence"
                    record["activity"].append(dict(step=story_step + 1, tool="finish", status="ok",
                                                   evidence_ids=[claim["evidence_id"] for claim in arguments["claims"]],
                                                   decision="Finished with checked evidence excerpts"))
                    break
                if name == "retrieve_material" and len(state["retrieved"]) >= settings.max_articles_per_story:
                    raise ValueError("Article retrieval limit reached")
                tool_result = tools.call(name, arguments)
                if name in {"inspect_related_stories", "compare_previous_briefings"} and arguments["story_id"] != story_id:
                    raise ValueError("Story inspection must stay within the current investigation")
                if name == "retrieve_material":
                    state["retrieved"][arguments["article_id"]] = tool_result
                else:
                    state["results"][name] = tool_result
                record["activity"].append(dict(step=story_step + 1, tool=name, arguments=arguments, status="ok",
                                               evidence_ids=[arguments["article_id"]] if name == "retrieve_material" else [],
                                               decision="Retrieved saved excerpt" if name == "retrieve_material" else "Inspected saved metadata"))
                provider.observe(action, tool_result)
            except Exception:
                record["status"] = "unavailable"
                status = getattr(provider, "last_http_status", None)
                if type(status) is int and 100 <= status <= 599:
                    record["provider_http_status"] = status
                record["activity"].append(dict(step=story_step + 1, tool="rejected_action", status="rejected",
                                               decision="Provider output or tool arguments could not be safely used"))
                break
        record["evidence_references"] = [dict(evidence_id=article_id, url=material["url"],
                                               scope=material["material_scope"], quarantined=material["quarantined"])
                                          for article_id, material in state["retrieved"].items()]
        record["what_changed"] = state["results"].get("compare_previous_briefings")
        related = state["results"].get("inspect_related_stories", {}).get("related", [])
        retrieved_ids = {article_id for article_id, material in state["retrieved"].items()
                         if article_id in target_ids and not material["quarantined"]}
        corroboration = sum(any(evidence_id(url) in retrieved_ids for url in group["evidence_urls"])
                            for group in candidate["reporting_groups"])
        record["corroboration"] = dict(retrieved_reporting_groups=corroboration,
                                       status="multiple_reporting_groups" if corroboration >= 2 else "limited")
        record["uncertainty"] = ["Only saved API excerpts were inspected. Full articles were not retrieved."]
        if corroboration < 2:
            record["uncertainty"].append("Independent corroboration is limited.")
        if candidate.get("has_rumor"):
            record["uncertainty"].append("Rumor wording appears in this story. Treat the claim as unconfirmed.")
        if related:
            record["uncertainty"].append("Related coverage shares names or teams and may describe a different event.")
        record["decision_summary"] = f"Read {len(state['retrieved'])} excerpts. Estimated reporting groups: {corroboration}. Scores unchanged."
        if record["summary"] and candidate.get("has_rumor"):
            record["summary"]["text"] = "Unconfirmed report. " + record["summary"]["text"]
    for candidate in briefing["candidates"] + briefing["stories"]:
        candidate["investigation"] = records[candidate["id"]]
        candidate["summary"] = records[candidate["id"]]["summary"]
        candidate["what_changed"] = records[candidate["id"]]["what_changed"]
    briefing["investigation"] = dict(provider=provider.name, status="complete" if all(record["status"] in {"complete", "insufficient_evidence"} for record in records.values()) else "partial",
                                     limits=asdict(settings), steps_used=steps,
                                     llm_calls=getattr(provider, "calls_made", llm_calls), provider_attempts=llm_calls,
                                     elapsed_seconds=max(0, clock() - started_at))
    return briefing
