"""Restore reporting dropped when the RSS reader selected the image caption."""
import hashlib
import os

import requests


API = "https://unionnewsms.com/wp-json/wp/v2/posts/5398"
LINK = "https://unionnewsms.com/local-news/union-county-unemployment-rises-to-3-1-in-october/"
OLD = "52d00ca85366724805f3071ab8bf9f85915b13b2e5dd39b69f9bea9fa4b84b85"
UPDATED = """<p>Union County’s unemployment rate rose to 3.1% in October from a revised 2.7% in September, according to preliminary figures from the Mississippi Department of Employment Security. The department counted 393 unemployed county residents in October, up 43 from the month before.</p>
<p>The number of employed residents fell by 67, from 12,477 in September to 12,410 in October. The county’s civilian labor force, which includes both employed and unemployed residents, fell by 24 to 12,803. The estimates count people where they live, so a Union County resident who commutes to a job in another county is included.</p>
<p>Union County’s rate remained below Mississippi’s 3.6% rate for October. The state and county figures used for this comparison are unadjusted for seasonal changes.</p>
<p>A separate table shows 26 initial unemployment insurance claims in Union County in October, up from 15 in September. Continued claims fell from 153 to 128. Those figures track insurance claims, while the unemployment estimates cover the resident labor force.</p>
<p><em>Sources: <a href="https://mdes.ms.gov/media/23357/labormarketdata.pdf">Mississippi Department of Employment Security monthly labor market report</a> and <a href="https://mdes.ms.gov/media/8735/urate.pdf">county unemployment rate series</a>.</em></p>"""


def main():
    with requests.Session() as client:
        client.auth = (os.environ["WORDPRESS_USERNAME"], os.environ["WORDPRESS_APP_PASSWORD"])
        def read():
            result = client.get(API, params={"context": "edit"}, timeout=20, allow_redirects=False)
            result.raise_for_status()
            return result.json()
        before = read()
        if (before["id"], before["link"], before["status"], before["featured_media"],
                before["title"]["raw"]) != (
                    5398, LINK, "publish", 5397, "Union County unemployment rises to 3.1% in October"):
            raise RuntimeError("Unexpected post identity")
        if before["content"]["raw"] != UPDATED:
            if before["modified_gmt"] != "2026-11-24T19:11:13" or hashlib.sha256(
                    before["content"]["rendered"].encode()).hexdigest() != OLD:
                raise RuntimeError("Published revision changed; inspect before editing")
            result = client.post(API, json={"content": UPDATED}, timeout=25, allow_redirects=False)
            result.raise_for_status()
        after = read()
        if after["content"]["raw"] != UPDATED or any(before[k] != after[k] for k in
                ("title","slug","status","featured_media","author","categories","tags","date_gmt")):
            raise RuntimeError("Could not verify the saved revision")
    page = requests.get(LINK, timeout=25)
    page.raise_for_status()
    if "Continued claims fell from 153 to 128." not in page.text:
        raise RuntimeError("Saved revision awaits public verification")
    print("Verified published post 5398 and original featured image 5397.", LINK)


if __name__ == "__main__":
    main()
