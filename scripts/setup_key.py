"""Run in your own terminal to save a Sail key without echo or shell history."""
import getpass
import os
from pathlib import Path
import sys
import warnings


def main():
    if not sys.stdin.isatty():
        raise SystemExit('Run this command directly in your terminal.')
    target = Path(__file__).resolve().parents[1] / '.env'
    if target.exists():
        raise SystemExit('A .env file already exists; left unchanged.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        key = getpass.getpass('Sail API key (hidden): ').strip()
    if not key or any(c.isspace() for c in key) or not key.isascii() or not key.isprintable():
        raise SystemExit('Expected a nonempty API key without whitespace. Nothing saved.')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write('SAIL_API_KEY=' + key + '\n')
    print('Saved privately to .env. No API requests made.')


if __name__ == '__main__':
    main()
