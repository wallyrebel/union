from datetime import datetime

from rss_to_wp.feeds.school_calendar import ZONE, break_notices


def test_break_notice_needs_both_dates_and_a_fixed_advance_window():
    header = '<p>New Albany, MS</p><a href="https://content.myconnectsuite.com/api/documents/abc123">District Calendar</a>'
    event = """<a class="cs-link" onclick="loadEventModal('{}','{} 9:00:00 AM','{} 9:00:00 AM')">{}</a>"""
    start = event.format("f"*36, "11/23/2026", "11/23/2026", "Thanksgiving Break Begins")
    back = event.format("a"*36, "11/30/2026", "11/30/2026", "Return From Thanksgiving Break")
    now = datetime(2026, 11, 20, 17, tzinfo=ZONE)
    assert not break_notices(header+start, now).entries
    entries = break_notices(header+start+back+start, now).entries
    assert len(entries) == 1
    assert "November 30" in entries[0].summary and "November 23" in entries[0].summary
    assert "9:00" not in entries[0].summary
    assert not break_notices(header+start+back, now.replace(day=23)).entries
