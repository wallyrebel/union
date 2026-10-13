"""Read-only reconciliation of one explicitly approved Union illustration."""
import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

from audit_preflight import NoRedirect

BASE = 'https://unionnewsms.com'
IMAGE_SHA256 = '6d492f1fd27b5181c23014d3d79516c751ad53df3be4b9d3e9160be1a420d440'
STEM = 'union-indoor-volleyball-illustration-6d492f1fd27b'
POST_IDS = (4742, 4744)


def pixels(data):
    with Image.open(BytesIO(data)) as image:
        image.load()
        return {'width': image.width, 'height': image.height,
                'rgba_sha256': hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest()}


def status_values(options):
    for endpoint in options.get('endpoints', []):
        if 'GET' not in endpoint.get('methods', []):
            continue
        status = endpoint.get('args', {}).get('status', {})
        values = status.get('enum') or status.get('items', {}).get('enum')
        if values:
            values = list(dict.fromkeys(values))
            if not {'inherit', 'private', 'trash'}.issubset(values):
                raise ValueError('Media status schema does not establish all-status coverage')
            return values
    raise ValueError('No readable media status schema')


def main():
    report = {'site': BASE, 'mode': 'read-only', 'verified': False,
              'image_sha256': IMAGE_SHA256, 'deterministic_stem': STEM,
              'target_posts': list(POST_IDS), 'matches': []}
    try:
        if os.environ['WORDPRESS_BASE_URL'].rstrip('/') != BASE:
            raise ValueError('Unexpected managed host')
        local = Path('review/assets/indoor-volleyball-illustration.png').read_bytes()
        if hashlib.sha256(local).hexdigest() != IMAGE_SHA256:
            raise ValueError('Approved image bytes changed')
        report['approved_pixels'] = pixels(local)
        token = base64.b64encode((os.environ['WORDPRESS_USERNAME'] + ':' + os.environ['WORDPRESS_APP_PASSWORD']).encode()).decode()
        opener = urllib.request.build_opener(NoRedirect())
        headers = {'Authorization': 'Basic ' + token, 'User-Agent': 'ApprovedIllustrationPreflight/1.0'}

        def get(path, params=None, method='GET'):
            url = BASE + path
            if params:
                url += '?' + urllib.parse.urlencode(params)
            with opener.open(urllib.request.Request(url, headers=headers, method=method), timeout=30) as response:
                return json.load(response)

        account = get('/wp-json/wp/v2/users/me', {'context': 'edit', '_fields': 'id,capabilities'})
        report['account_id'] = account['id']
        report['upload_files'] = account.get('capabilities', {}).get('upload_files') is True
        if not report['upload_files']:
            raise ValueError('Managed account cannot upload media')
        options = get('/wp-json/wp/v2/media', method='OPTIONS')
        statuses = status_values(options)
        report['statuses_checked'] = statuses
        found = {}
        for status in statuses:
            items = get('/wp-json/wp/v2/media', {'context': 'edit', 'status': status,
                        'search': STEM, 'per_page': 100,
                        '_fields': 'id,author,slug,status,source_url,media_details,caption,alt_text'})
            if not isinstance(items, list) or len(items) >= 100:
                raise ValueError('Ambiguous or unbounded media result')
            for item in items:
                found[item['id']] = item
        for item in found.values():
            if STEM not in item.get('slug', '') and STEM not in item.get('source_url', ''):
                raise ValueError('Search returned a different media identity')
            source = item['source_url']
            if urllib.parse.urlsplit(source).hostname != 'unionnewsms.com':
                raise ValueError('Unexpected original-media host')
            with urllib.request.urlopen(source, timeout=30) as response:
                observed = pixels(response.read())
            report['matches'].append({**item, 'observed_pixels': observed,
                                      'pixels_match': observed == report['approved_pixels']})
        report['posts'] = []
        for pid in POST_IDS:
            post = get('/wp-json/wp/v2/posts/' + str(pid),
                       {'context': 'edit', '_fields': 'id,author,status,link,featured_media,modified_gmt'})
            if post['id'] != pid or post['author'] != account['id'] or post['status'] != 'publish':
                raise ValueError('Unexpected target post identity or ownership')
            report['posts'].append(post)
        report['verified'] = True
    except Exception as exc:
        report['error_type'] = type(exc).__name__
        if isinstance(exc, urllib.error.HTTPError):
            report['http_status'] = exc.code
        elif isinstance(exc, ValueError):
            report['reason'] = str(exc)
    path = Path('data/approved-image-preflight.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
