# Injury corroboration

Live refreshes can now use their reserved targeted request for either a game
or an injury. The total GNews budget, shared collection deadline, pause before
the targeted request, and failure handling are unchanged.

## Selection

The collector considers the newest candidate with one estimated reporting group.
An injury is eligible only when its saved metadata identifies one player and
one body part. The generated query is the normalized player name, body part,
and `injury`, such as `luka doncic back injury`.

All seed articles must be old enough for GNews's 12-hour delay. Vague injury
headlines do not generate player-only searches. A one-request budget still
runs discovery only. Trades remain outside automatic corroboration.

## Keeping updates together

Reports about the same player and body part can join one candidate within the
existing 72-hour window, even when a later report mentions a different opponent.
Different players, different body parts, conflicting left/right sides, and
reports outside that window stay separate. Vague reports continue to require
text similarity instead of merging on the player name alone.

Availability phrases in the primary headline clause take precedence over the
opening description. Questionable or expected-return language is marked
uncertain. Negated clearance does not count as a return, and a return-timeline
headline alone does not establish availability.

An injury candidate uses the latest dated report with an identified availability
phrase as its headline. The dashboard's expandable Injury updates panel lists
the inferred availability, date, original headline, publisher, and source link.
These are attributed reports, not an independently verified current status.
Restricted feed material suppresses the derived update history for that candidate.

Parsed availability does not establish a reviewed substantive development or
automatically award freshness points. Coverage, momentum, and freshness remain
deterministic and retain their configured evidence requirements.

## Verification

On November 10, 2026, the automatically generated `luka doncic back injury`
query was tested with one live GNews request. It returned seven articles:
five included and two held for review. Four estimated reporting groups formed
one eligible injury story, with dated reports progressing from questionable,
to unavailable, to available. The Quentin Grimes injury stayed separate.

The full automatic selection and request-budget path is covered with simulated
API responses. The live check verified the generated query and downstream
processing, rather than running a complete dashboard refresh. No LLM requests
were made. Saved live data is in the ignored `artifacts/injury-search/` folder.

## Limits

These rules use names and phrases rather than a full player database or event
model. A repeated injury to the same body part within 72 hours can still merge,
and missing body parts or unclear names can leave related coverage separate.
Availability inference can miss complex negation or conflicting accounts. The
dated source links remain the evidence. Reporting groups do not establish
publisher ownership independence or original authorship.
