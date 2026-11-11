"""Collect attributed headlines from FreeNewsApi.ai with fixed request limits."""
from collections import Counter
from datetime import datetime, timezone
from html import unescape
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlencode, urlsplit

from scripts.validate_gdelt import SourceError, canonical_url, format_time
from .stories import inspect_article, parse_date, clean_text

SETTINGS_FILE = Path(__file__).resolve().parents[1] / 'config/free-news.json'
ENDPOINT = 'https://freenewsapi.ai/v1/search'


def load_key(env_file):
    key = os.environ.get('FREE_NEWS_API_KEY', '').strip()
    if not key and env_file and Path(env_file).is_file():
        for line in Path(env_file).read_text().splitlines():
            name, separator, value = line.partition('=')
            if separator and name.strip() == 'FREE_NEWS_API_KEY':
                key = value.strip().strip('\"\'')
                break
    if key and not re.fullmatch(r'[A-Za-z0-9_-]{8,200}', key):
        raise SourceError('FREE_NEWS_API_KEY is invalid. Check the server .env entry.')
    return key or None


def load_settings(path=SETTINGS_FILE):
    settings = json.loads(Path(path).read_text())
    if not isinstance(settings, dict) or set(settings) != {'max_requests', 'corroboration_requests', 'max_articles_per_publisher', 'publishers'}:
        raise ValueError('Invalid FreeNewsApi.ai settings')
    for name, maximum in [('max_requests', 3), ('max_articles_per_publisher', 50)]:
        if type(settings[name]) is not int or not 1 <= settings[name] <= maximum:
            raise ValueError('Invalid FreeNewsApi.ai collection limit')
    if type(settings['corroboration_requests']) is not int or settings['corroboration_requests'] not in (0, 1):
        raise ValueError('FreeNewsApi.ai allows at most one targeted search')
    publishers = settings['publishers']
    if not isinstance(publishers, dict) or not 1 <= len(publishers) <= 24 or any(
            not isinstance(host, str) or not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}', host)
            or not isinstance(name, str) or not name.strip() for host, name in publishers.items()):
        raise ValueError('FreeNewsApi.ai publishers need exact hosts and display names')
    return settings


def fetch_page(url, key, timeout):
    try:
        response = subprocess.run([
            'curl', '--disable', '--silent', '--max-time', str(timeout),
            '--connect-timeout', str(min(timeout, 8)), '--max-filesize', '2000000',
            '--proto', '=https', '--header', '@-', '--write-out', '\n%{http_code}', url],
            input=f'Authorization: Bearer {key}\n', capture_output=True, text=True, timeout=timeout + 0.2)
        if response.returncode:
            raise SourceError('FreeNewsApi.ai connection failed')
        body, status = response.stdout.rsplit('\n', 1)
        if status != '200':
            errors = {'401': 'API key rejected', '402': 'Free quota exhausted', '429': 'Rate limit reached'}
            raise SourceError('FreeNewsApi.ai: ' + errors.get(status, 'Request failed') + '. No retry was made.')
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get('results'), list) or len(data['results']) > 100:
            raise SourceError('FreeNewsApi.ai returned an invalid result page')
        return data
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        raise SourceError('FreeNewsApi.ai response unavailable or invalid') from None


def parse_article(row, publishers, start, end, collected_at):
    if not isinstance(row, dict) or not isinstance(row.get('title'), str) or not 1 <= len(row['title'].strip()) <= 2000:
        raise ValueError('Missing or invalid headline')
    if not isinstance(row.get('url'), str) or not 1 <= len(row['url']) <= 6000:
        raise ValueError('Missing or invalid article URL')
    canonical = canonical_url(row['url'])
    host = urlsplit(canonical).hostname
    provider_host = urlsplit(row['url']).hostname
    if provider_host not in publishers or row.get('host') != provider_host:
        raise ValueError('Publisher host does not match the reviewed list')
    published = parse_date(row.get('published_at'))
    if not start <= published < end:
        raise ValueError('Publication timestamp outside the requested window')
    date_source = row.get('date_source')
    if date_source not in {None, 'jsonld', 'meta', 'extracted'}:
        raise ValueError('Publication date is based on crawl time or unknown provenance')
    basis = 'FreeNewsApi.ai supplied, not independently verified'
    basis += f' ({date_source})' if date_source else '. Date provenance was not supplied.'
    author = clean_text(row['author']) if isinstance(row.get('author'), str) else ''
    origin = None
    for label, pattern in [('associated-press', r'\b(associated press|ap news)\b'),
                           ('reuters', r'\breuters\b'), ('afp', r'\b(afp|agence france presse)\b')]:
        if re.search(pattern, author):
            origin = label
            break
    if re.search(r'\bshams\b', row['title'], re.I):
        origin = 'shams-charania'
    try:
        crawled_at = format_time(parse_date(row.get('crawled_at')))
    except ValueError:
        crawled_at = None
    return dict(title=unescape(row['title']).strip(), url=row['url'], canonical_url=canonical,
                publisher_host=host, publisher_name=publishers[provider_host], source_url='https://' + provider_host,
                published_at=format_time(published), collected_at=collected_at,
                publication_date_basis=basis, provider_crawled_at=crawled_at,
                description=None, content_excerpt=None, collection_sources=['free-news-api'],
                material_policy='headline_only', metadata_only=True, investigation_allowed=False,
                reporting_origin=origin,
                attribution_note='Headline discovered through FreeNewsApi.ai. Publisher date and original authorship are unverified.')


def collect_headlines(key, start, end, settings=None, transport=fetch_page, max_seconds=30,
                      clock=time.monotonic, sleep=time.sleep, query='NBA', sort='date'):
    settings = settings or load_settings()
    deadline = clock() + max_seconds
    hosts = list(settings['publishers'])
    batch_count = min(settings['max_requests'], len(hosts))
    articles, attempts, seen, counts = [], [], set(), Counter()
    rejected, filtered, capped, missing_provenance = 0, 0, 0, 0
    for index in range(batch_count):
        if index:
            if deadline - clock() <= 1:
                break
            sleep(0.6)
        remaining = deadline - clock()
        if remaining <= 0.5:
            break
        batch = hosts[index::batch_count]
        url = ENDPOINT + '?' + urlencode(dict(q=query, lang='en', host=','.join(batch),
            **{'from': format_time(start), 'to': format_time(end)}, sort=sort, size=100, full_text='false'))
        attempt = dict(source='free-news-api', status='failed', hosts=batch, count=0)
        attempts.append(attempt)
        try:
            data = transport(url, key, min(12, remaining - 0.2))
            rows = data['results']
            if not isinstance(rows, list) or len(rows) > 100:
                raise SourceError('FreeNewsApi.ai returned an invalid result page')
            attempt.update(status='ok', count=len(rows))
            collected_at = format_time(datetime.now(timezone.utc))
            for row in rows:
                try:
                    article = parse_article(row, {host: settings['publishers'][host] for host in batch}, start, end, collected_at)
                    if article['canonical_url'] in seen:
                        continue
                    seen.add(article['canonical_url'])
                    if inspect_article(article)[0] == 'excluded':
                        filtered += 1
                        continue
                    host = article['publisher_host']
                    if counts[host] >= settings['max_articles_per_publisher']:
                        capped += 1
                        continue
                    counts[host] += 1
                    missing_provenance += int(row.get('date_source') is None)
                    articles.append(article)
                except (ValueError, KeyError, TypeError):
                    rejected += 1
        except SourceError:
            attempt['error'] = 'FreeNewsApi.ai request failed. No retry was made.'
            break
    succeeded = any(attempt['status'] == 'ok' for attempt in attempts)
    status = dict(id='free-news-api', name='FreeNewsApi.ai', kind='api', status='partial' if succeeded else 'failed' if attempts else 'skipped',
                  article_count=len(articles), collected_at=format_time(datetime.now(timezone.utc)) if succeeded else None,
                  complete_window=False, rejected_records=rejected, filtered_records=filtered, capped_records=capped,
                  missing_date_provenance=missing_provenance,
                  note='Bounded headline discovery from reviewed hosts. Publisher dates and independent reporting are unverified. Pages may cover only part of the window.')
    if succeeded:
        status['available_end'] = format_time(end)
    if any(attempt['status'] == 'failed' for attempt in attempts):
        status['error'] = 'FreeNewsApi.ai could not complete collection.'
    return articles, status, attempts


def main():
    import argparse
    from datetime import timedelta

    root = SETTINGS_FILE.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, choices=range(1, 8), default=7)
    parser.add_argument('--output', type=Path, default=root / 'artifacts/free-news-check/report.json')
    args = parser.parse_args()
    try:
        key = load_key(root / '.env')
        if not key:
            raise SourceError('Set FREE_NEWS_API_KEY in the server .env file first.')
        settings = load_settings()
    except (SourceError, ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=args.days)
    articles, status, attempts = collect_headlines(key, start, end, settings)
    report = dict(provider='Monitored sources', mode='live', requested_start=format_time(start),
                  requested_end=format_time(end), searchable_end=format_time(end), freshness_delay_hours=0,
                  generated_at=format_time(datetime.now(timezone.utc)), complete_available_results=False,
                  articles=articles, sources=[status], attempts=attempts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(f"Retained {len(articles)} headlines from {len({a['publisher_name'] for a in articles})} publishers in {len(attempts)} requests.")
    print(f"Source status: {status['status']}. Saved metadata: {args.output}")
    return 0 if status['status'] == 'partial' else 1


if __name__ == '__main__':
    raise SystemExit(main())
