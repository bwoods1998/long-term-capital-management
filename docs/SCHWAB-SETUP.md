# Private Schwab access

The optional connector supports browser authorization and private account snapshots. It cannot submit orders. An **Accounts and Trading Production** app can carry broader permissions than this connector uses; the separate Market Data app is not needed here.

Live access requires the account owner's browser consent. Local setup and offline tests do not establish that an account is connected or that a live request has succeeded.

## Install once

Run these commands from the repository. Create the virtual environment only if `.venv` does not already exist:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-schwab.txt
```

The optional requirements pin **schwab-py 1.5.1** and **Authlib 1.8.0**. [schwab-py](https://github.com/alexgolec/schwab-py) is a community client, not an official Schwab SDK. The research commands still run with system Python and the standard library.

## Save the app credentials

Skip this step if the credentials are already saved:

```sh
python3 scripts/setup_schwab.py
```

Enter the registered callback exactly; the prompt defaults to `https://127.0.0.1`. Hidden prompts collect the app client ID and secret. The script saves `.data/schwab/credentials.json` with owner-only permissions, refuses replacement or symlinks, and makes no network requests. It leaves the Sail `.env` intact.

App credentials identify this application. They do not authorize it to read your brokerage account.

## Authorize in your terminal

```sh
.venv/bin/python schwab_connect.py status
.venv/bin/python schwab_connect.py login
```

`status` reads local metadata only. It neither contacts Schwab nor proves stored tokens are still accepted.

`login` opens Schwab in your browser. Sign in there, review the permissions, and choose the accounts you want to authorize. After consent, the browser returns to the registered callback. With `https://127.0.0.1`, an unreachable-page error is expected: this manual flow does not run a local HTTPS server.

Copy the **entire returned URL from the address bar** into the command's hidden terminal prompt. Do not change the callback or add a port to fix the browser error. The returned URL contains a temporary authorization code; it belongs only in that local prompt, never in chat, screenshots, command arguments, commits, or public logs.

The connector exchanges that code and saves tokens privately, bound to the app configuration that created them. Existing tokens or a pending login require an explicit restart:

```sh
.venv/bin/python schwab_connect.py login --restart
```

Use restart only when you intend to begin fresh authorization. Schwab's guide warns that starting authorization and then abandoning it can invalidate earlier tokens. Other commands do not silently begin a new browser authorization.

## Read one account

```sh
.venv/bin/python schwab_connect.py snapshot
```

Each read requests authorized account identifiers to check that the saved selection is still available. If no account has been selected locally, choose from the masked list. Later reads use that saved selection; `snapshot --select-account` opens account selection again.

The account read saves `.data/schwab/account-snapshot.json` with an observation timestamp, `reconciled: false`, and the original JSON in `response_body`. Keeping the response text preserves the exact numeric spelling for later decimal accounting. The public research export does not read this directory.

Account reads may refresh an expired access token. Expiry follows the token response and provider behavior; this project does not promise a fixed refresh-token lifetime. If a refresh result cannot be confirmed, the connector blocks further account reads instead of repeating the exchange. Inspect `status`, then use `login --restart` when ready to complete fresh authorization.

This is a private observation, not a reconciled return series. There are no order requests, public account exports, or public portfolio-performance calculations in this connector.

## Documentation basis

The owner-provided official OAuth guide established exact callback matching, access/refresh tokens, and the authorization-restart warning. The installed community client's source supplies the request implementation; the complete authenticated official account specification was not readable in this development environment. Do not describe this as an official SDK or a live-verified integration before the owner's authorization and first account read succeed.

Official entry points: [OAuth guide](https://developer.schwab.com/user-guides/get-started/authenticate-with-oauth), [Individual Trader API documentation](https://developer.schwab.com/products/trader-api--individual/details/documentation/Retail%20Trader%20API%20Production). Implementation reference: [schwab-py source](https://github.com/alexgolec/schwab-py).

For the concepts behind the flow, read [Lesson 3: private account access](history/lessons/03-schwab-access.md).
