"""Build clearly labeled fictional articles for trying the app without services."""
from datetime import timedelta

from scripts.validate_gdelt import format_time


def sample_report(now, days):
    start, end = now - timedelta(days=days), now - timedelta(hours=12)
    first_time = end - timedelta(hours=3)
    second_time = end - timedelta(hours=1)
    games = [
        ("lakers-celtics", "Sample: Celtics beat Lakers in a fictional game",
         "Sample: Celtics win a fictional game against Lakers",
         "The Boston Celtics beat the Los Angeles Lakers 110-100 in this fictional NBA game.",
         "The Boston Celtics win 110-100 against the Los Angeles Lakers in this sample NBA game."),
        ("hawks-nets", "Sample: Hawks beat Nets in a fictional game",
         "Sample: Nets lose as Hawks win a fictional game",
         "The Atlanta Hawks beat the Brooklyn Nets 108-104 in this fictional NBA game.",
         "The Brooklyn Nets lost 108-104 to the Atlanta Hawks in this sample NBA game."),
    ]
    articles = []
    for slug, first_title, second_title, first_text, second_text in games:
        for publisher, title, text, published in [
                ("alpha", first_title, first_text, first_time),
                ("bravo", second_title, second_text, second_time)]:
            articles.append(dict(title=title, url=f"https://{publisher}.example.com/sample/{slug}",
                                 publisher_name=f"Sample newsroom {publisher}", publisher_host=f"{publisher}.example.com",
                                 published_at=format_time(published), collected_at=format_time(now),
                                 description=text, content_excerpt=text))
    return dict(provider="Sample", mode="sample", generated_at=format_time(now),
                requested_start=format_time(start), requested_end=format_time(now), searchable_end=format_time(end),
                freshness_delay_hours=12, complete_available_results=True, articles=articles,
                attempts=[], stop_reason="Fictional sample data selected explicitly")
