# Prepare a private Schwab connection

This stage stores application credentials locally. It does not authorize an account, make API requests, fetch balances, or place orders. The initial connector will expose account reads; an Accounts and Trading credential may carry broader authority than that connector uses.

Use the approved **Accounts and Trading Production** app's client ID and secret. The separate Market Data app is not needed for this setup. Run this directly in your Linux terminal from the repository:

```sh
python3 scripts/setup_schwab.py
```

Enter the app's registered callback exactly; the prompt defaults to `https://127.0.0.1`. The client ID and secret prompts hide your input. Do not put credentials in command arguments, chat, screenshots, source code, or shell history. A returned authorization URL may contain a temporary code and is not the registered callback.

The script saves `.data/schwab/credentials.json` with owner-only permissions and refuses to replace an existing file or follow symlinks. It leaves the Sail `.env` file intact. All of `.data/` is Git-ignored. Nothing from this file belongs in the public research snapshot or personal-site assets.

## Before account authorization

Current official OAuth and account specifications still need to be checked against the owner's authenticated developer portal. The public OAuth guide was inaccessible from this development environment on September 12, 2026, including a fresh browser attempt. No authorization endpoints, token lifetimes, or undocumented refresh behavior have been implemented by assumption.

From the portal's authentication guide, obtain the authorization request example, token exchange, refresh-token request, callback requirements, and any scope, state, or PKCE instructions. Documentation with placeholders is sufficient; exclude real credentials, returned authorization codes, access tokens, refresh tokens, and account information.

Then inspect the account identifier, balances, and positions endpoint specifications before implementing the private adapter. Account selection and permission are part of the browser authorization step. Keep account observations private while reconciliation and public-display permissions are established.

Official entry points: [OAuth guide](https://developer.schwab.com/user-guides/get-started/authenticate-with-oauth), [Individual Trader API documentation](https://developer.schwab.com/products/trader-api--individual/details/documentation/Retail%20Trader%20API%20Production).
