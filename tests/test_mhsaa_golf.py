from datetime import datetime, timezone

import pytest

from rss_to_wp.feeds.golf import scorecard, unsupported_tie_method

URL = "https://www.misshsaa.com/2026/11/22/team-golf/"
DATE = datetime(2026, 11, 22, tzinfo=timezone.utc)
PAGE = """
<link rel="canonical" href="https://www.misshsaa.com/2026/11/22/team-golf/">
<article><div class="entry"><div><p>Golf</p><p>2026 MHSAA Class 1A Boys Golf Championship</p>
<p>Class 1A</p><p>Oct. 26</p><p>Example Course</p><p>Example, MS</p></div>
<div><details><summary>All teams</summary><div><div><p>T2</p><p>Example Eagles</p>
<p>310 + 313</p><p>623 (+47)</p></div></div></details></div>
<section><h2>Individual Results</h2><div><div><p>T6</p><div><p>Example Player</p>
<p>Example</p></div><p>76 + 77</p><p>153 (+9)</p></div></div></section></div></article>
"""


def test_local_result_preserves_ties_dates_and_source_identity():
    result = scorecard(PAGE, URL, {"Example Eagles": "Example"}, DATE)
    assert result
    title, facts = result
    assert "ties for 2nd" in title
    for detail in ("place T2", "place T6", "76 + 77", "November 22, 2026", "Oct. 26"):
        assert detail in facts
    assert scorecard(PAGE, URL, {"Another School": "Another"}, DATE) is None
    assert scorecard(PAGE.replace("623 (+47)", "624 (+48)"), URL, {"Example Eagles": "Example"}, DATE) is None
    with pytest.raises(ValueError):
        scorecard(PAGE, URL + "other/", {"Example Eagles": "Example"}, DATE)


def test_tied_totals_do_not_establish_a_playoff():
    assert unsupported_tie_method("Both schools finished at 644.", {"excerpt": "The title went to a playoff."})
    assert not unsupported_tie_method("Both schools finished at 644.", {"body": "The standings list the Eagles first."})
