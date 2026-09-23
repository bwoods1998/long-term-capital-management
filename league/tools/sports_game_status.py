"""Read game status from an existing, explicitly identified scoreboard event.

Declare, for example, NEEDS['feeds'] = {'sports': ['mlb']}, then use:

    from tools.sports_game_status import game_status
    state = game_status(ctx, 'mlb', verified_event_id)
    if state is not None and state['pregame']:
        # The supplied board reports pre-game and its start is still ahead.
        pass

verified_event_id must be the exact string ID of an ESPN event in the supplied
league board. This module does NOT establish which event a Kalshi market refers
to. Use an independently verified association; never guess from hours_to_close,
a ticker fragment, or a fuzzy team name. A House-provided market/event mapping
is not currently part of the contract.

Return a new dict with event_id, received_at, start_time, hours_to_start,
status, completed, pregame, and in_progress. hours_to_start is signed:
positive before the scheduled start, negative afterward. status is the source's
pre/in/post value. pregame requires reported 'pre' AND a strictly future start.
in_progress is True for 'in', False for 'post' or a future-start 'pre', and None
for 'pre' at/after its scheduled start. Do not use 'not in_progress' as an entry
condition: unknown and completed events are not pre-game opportunities.

Missing feeds/events, duplicate matching IDs, invalid required fields,
contradictory status/completion, and receipts after ctx['now'] return None.
None is unavailable information, not a false status or zero hours. Required
timestamps must be ISO strings with an explicit UTC offset (Z is accepted).

All calculations use ctx['now']; no system clock or external data is consulted.
Inputs are not modified. No freshness cutoff is inferred from the feed's t:
unchanged content can keep an old receipt time. This helper reports the supplied
observation, not guaranteed current truth, a fill opportunity, or player-prop
state. Scheduled time alone never proves that a game has actually begun.
Historical availability is limited to the House's recorded feed coverage.
"""

from datetime import datetime, timezone


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return None
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def game_status(ctx, league, event_id):
    """Return conservative event status, or None when it cannot be established.

    league and event_id are exact, nonempty strings. ctx is the unmodified
    decision context containing now and feeds.sports[league]. See the module
    docstring for identity requirements and the three-valued in_progress field.
    """
    if not isinstance(ctx, dict):
        return None
    if not isinstance(league, str) or not league:
        return None
    if not isinstance(event_id, str) or not event_id:
        return None
    now = _timestamp(ctx.get('now'))
    if now is None:
        return None
    feeds = ctx.get('feeds')
    if not isinstance(feeds, dict):
        return None
    sports = feeds.get('sports')
    if not isinstance(sports, dict):
        return None
    board = sports.get(league)
    if not isinstance(board, dict) or board.get('league') != league:
        return None
    received = _timestamp(board.get('t'))
    if received is None or received > now:
        return None
    events = board.get('events')
    if not isinstance(events, list):
        return None
    matches = [event for event in events
               if isinstance(event, dict) and event.get('id') == event_id]
    if len(matches) != 1:
        return None
    event = matches[0]
    start = _timestamp(event.get('start'))
    status = event.get('status')
    completed = event.get('completed')
    if start is None or status not in ('pre', 'in', 'post'):
        return None
    if not isinstance(completed, bool) or completed != (status == 'post'):
        return None
    hours = (start - now).total_seconds() / 3600.0
    pregame = status == 'pre' and hours > 0.0
    in_progress = status == 'in'
    if status == 'pre' and not pregame:
        in_progress = None
    return {
        'event_id': event_id,
        'received_at': board['t'],
        'start_time': event['start'],
        'hours_to_start': hours,
        'status': status,
        'completed': completed,
        'pregame': pregame,
        'in_progress': in_progress,
    }
