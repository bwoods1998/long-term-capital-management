"""Read-only Sail preflight. Never prints credentials or raw API responses."""
import json
from decimal import Decimal
from pathlib import Path
import stat
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    path = Path(__file__).resolve().parents[1] / '.env'
    if path.is_symlink() or not path.is_file():
        raise SystemExit('Run scripts/setup_key.py first; .env must be a regular file.')
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SystemExit('Restrict .env permissions with chmod 600 .env before continuing.')
    entries = [line.partition('=') for line in path.read_text().splitlines() if line.startswith('SAIL_API_KEY=')]
    if len(entries) != 1 or not entries[0][2]:
        raise SystemExit('Expected exactly one nonempty SAIL_API_KEY in .env.')
    key = entries[0][2]
    opener = build_opener(NoRedirect)

    def get(route):
        request = Request('https://api.sailresearch.com' + route,
                          headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}, method='GET')
        try:
            with opener.open(request, timeout=30) as response:
                return json.loads(response.read(2_000_000), parse_float=Decimal)
        except HTTPError as error:
            raise SystemExit(f'Sail preflight returned HTTP {error.code}. No response body or key printed.') from None
        except (URLError, TimeoutError, ValueError):
            raise SystemExit('Sail preflight could not complete. No credentials printed.') from None

    models = get('/v1/models')
    ids = {item['id'] for item in models.get('data', [])}
    print('Authentication succeeded. Model catalog entries:', len(ids))
    for model in ['deepseek-ai/DeepSeek-V4-Flash-0731', 'google/gemma-4-31B-it', 'zai-org/GLM-5.3']:
        print(model + ': ' + ('listed' if model in ids else 'not listed'))
    usage = get('/v2/usage/summary?range=period')
    if usage.get('available') is True and usage.get('has_metronome_customer') is True and usage.get('balance_unavailable') is False and isinstance(usage.get('balance'), (int, Decimal)):
        balance = Decimal(usage['balance']) / 100
        if not balance.is_finite():
            raise SystemExit('Balance unavailable; check Sail dashboard.')
        print(f'Reported credit balance: ${balance:.2f} (billing data may lag).')
    else:
        print('Credit balance not confirmed; check Sail dashboard.')
    print('Read-only checks complete. No inference requests or cloud resources created.')


if __name__ == '__main__':
    main()
