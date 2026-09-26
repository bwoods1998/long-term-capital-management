# Lesson 3: private account access

The application can be configured while the account is still disconnected. OAuth is the step that joins them—with the owner's permission.

| State | What it establishes | What it does not establish |
|---|---|---|
| App credentials saved | The connector can identify the registered application | Permission to read an account |
| Browser consent completed | The owner authorized selected accounts and the code exchange produced tokens | That every future request will succeed |
| Account snapshot saved | A request returned a dated account observation | Reconciled investment returns or permission to publish account data |

## Predict before running

After completing [setup](../SCHWAB-SETUP.md), run the local status command:

```sh
.venv/bin/python schwab_connect.py status
```

Before authorizing, write down why a saved client ID and secret cannot substitute for account consent. Also predict whether local status can prove a token has not been revoked at Schwab.

## Follow the handoff

```text
Local connector → Schwab sign-in and account consent
               ← Returned callback URL with temporary code
Local connector → Token exchange → Private token storage
Local connector → Selected account read → Private snapshot
```

The **registered callback** is the fixed destination supplied when the app was configured. The **returned URL** includes temporary authorization data. With this manual flow, the browser may show an unreachable page at `https://127.0.0.1`: there is no local HTTPS server. The URL still carries the result. Copy its full value into the hidden terminal prompt, never into chat or a command argument.

An **access token** accompanies API requests. A **refresh token** can obtain a replacement access token without another browser sign-in, while the provider still permits it. Refresh follows returned expiry information; it is not a guarantee of perpetual access. Fresh **authorization** requires owner interaction again and is a separate action.

## Read, then explain

Run `login`, complete consent, and then run `snapshot` using the commands in the setup guide. Keep the resulting account data local. Compare the snapshot's timestamp and selected account with the brokerage interface; differences need explanation before treating the data as a portfolio ledger.

Explain these three cases in your own words:

1. Local status finds tokens, but Schwab rejects the next request. Why can both observations be correct?
2. A token-refresh request may have succeeded, but its response was lost. Why can blindly retrying create more uncertainty?
3. The account value rises after a deposit. What information is missing before calling the increase an investment return?

The connector blocks further account reads after an uncertain refresh and does not silently start a new authorization. Recovery requires explicit `login --restart`, which is deliberate because beginning a new authorization can affect earlier tokens. The public research ledger remains separate from this private account workflow.
