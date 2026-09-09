# MILESTONE-084 — Broker and Market-Data Research

**This milestone contacted no broker, opened no account, accepted no terms,
created no credential, subscribed to no data feed and submitted no order.**
This document selects a *target for a future milestone*. It is research and
interface selection only. Nothing here authorizes any of the above.

> **Supersedes** the earlier Phase C version of this document, which reached
> its conclusion from search results without separating what it had verified
> from what it had merely read. That separation is now the document's spine.

---

## 1. What this environment could and could not verify

The single most important thing about this research is where each fact came
from, so that is settled before any claim is made.

This container's network policy answers `403` to `CONNECT` for every one of the
three brokers' own documentation domains. Measured, not assumed:

| Host | Result |
|---|---|
| `alpaca.markets` | blocked (`000` / proxy `403 CONNECT`) |
| `docs.alpaca.markets` | blocked |
| `www.interactivebrokers.com` | blocked |
| `interactivebrokers.github.io` | blocked |
| `www.developer.saxo` | blocked |
| `saxobank.github.io` | blocked |
| `github.com`, `raw.githubusercontent.com` | reachable |
| `pypi.org` | reachable |

Every fact below therefore carries one of three tiers, and the tier is part of
the fact:

**`VERIFIED-PRIMARY`** — read directly, in this session, from a source the
vendor itself publishes: their official SDK source on GitHub, or their official
package metadata on PyPI. Good evidence for API surface: endpoints, enum
values, method names, environment separation.

**`UNVERIFIED-SECONDARY`** — obtained from web search summaries of the vendors'
documentation. The underlying pages are the vendors' own, but this environment
could not open them, so what is recorded is a *report* of the page, not the
page. Everything commercial and contractual is in this tier: pricing, market
data entitlements, account-opening prerequisites, regional eligibility.

**`NOT-VERIFIABLE-HERE`** — requires an account, a login, or a signed
agreement. Out of scope by the mission's own prohibition.

A tier is never upgraded by confidence. §6 is the checklist that lets the
Owner, on an unrestricted network, convert the second tier into the first.

---

## 2. What was read directly (VERIFIED-PRIMARY)

### 2.1 Alpaca — official SDK `alpacahq/alpaca-py`

Read from `raw.githubusercontent.com/alpacahq/alpaca-py/master/alpaca/trading/`.

- **Paper and live are different base URLs selected by one boolean.** From
  `client.py`: `base_url=(url_override if url_override else
  BaseURL.TRADING_PAPER if paper else BaseURL.TRADING_LIVE)`, with the
  constructor documenting `paper (bool): True is paper trading should be
  enabled.` A single flag separates simulated from real money.
- **The order-submission method is `submit_order`**, declared
  `def submit_order(self, order_data: OrderRequest) -> Union[Order, RawData]:`.
- **`OrderType`** = `market`, `limit`, `stop`, `stop_limit`, `trailing_stop`.
- **`TimeInForce`** = `day`, `gtc`, `opg`, `cls`, `ioc`, `fok`.
- **`OrderSide`** = `buy`, `sell`.
- **`AccountStatus`** includes a distinct `PAPER_ONLY` member, so "paper only"
  is a first-class account state in the vendor's own model rather than a
  convention.

**Direct consequence for M084's safety boundary.** M084's architecture
deny-list names `alpaca` and blocks it package-wide; `submit_order` is the
exact symbol that would have to appear for a submission to exist. The
deny-list is aimed at the real method name, not a guess at one. Family 27 of
the mutation campaign removes `alpaca` from that list and the boundary tests
fail, so the aim is checked rather than asserted.

M084 fits this surface without needing any of it: its intents are `BUY` /
`MARKET` or `LIMIT` / `DAY`, all of which exist above.

### 2.2 Interactive Brokers — official package `ibapi` on PyPI

Read from `pypi.org/pypi/ibapi/json`.

- Author/maintainer **IBG LLC**, contact `@interactivebrokers.com`; summary
  **"Official Interactive Brokers API"**. This is the vendor's own package.
- Home page `interactivebrokers.github.io/tws-api` — **blocked here**, so the
  API surface itself could not be read the way Alpaca's was.
- License: **IB API Non-Commercial License or IB API Commercial License**
  (proprietary, not OSI). A licence decision belongs to the Owner, and it is
  flagged here rather than absorbed silently.

### 2.3 Saxo Bank

No official Saxo SDK was reachable from `github.com` or `pypi.org` in this
session, and the developer portal is blocked. **Saxo has no VERIFIED-PRIMARY
row in this document.** That is a gap in the evidence, not a finding about
Saxo, and it is why Saxo is not the preferred target below.

---

## 3. What was read only as search summaries (UNVERIFIED-SECONDARY)

Every row here is a *report of* a vendor page this environment could not open.
None of it may be relied on without §6.

| # | Claim | Vendor | Bearing |
|---|---|---|---|
| S-1 | A paper-only account can be created by anyone globally with just an email address; no funding, no minimum, no identity verification; available immediately. | Alpaca | Decisive if true |
| S-2 | Paper base URL is `https://paper-api.alpaca.markets`. | Alpaca | High |
| S-3 | The free/Basic plan provides IEX real-time data only; SIP consolidated data requires a paid subscription; a Paper Only account is entitled to IEX. | Alpaca | High |
| S-4 | A paper trading account is opened from Account Management **once the regular account is approved and funded**; new clients receive a paper account with 1,000,000 USD notional. | IBKR | Decisive if true |
| S-5 | Real-time data requires trading permissions, **a funded account**, and per-username market-data subscriptions, with paper users treated as an exception. | IBKR | High |
| S-6 | The SIM environment is a copy of live with a simulated 100,000 account value, and a **free** developer account can be created for it. | Saxo | Decisive if true |
| S-7 | Market data and reporting are **not fully available in SIM**; portal tokens are one-day and simulation-only. | Saxo | High |

**S-4 is the pivotal claim of this entire document.** If IBKR paper access
genuinely requires an approved and funded live account, then IBKR cannot be
reached at all under the constraint that governs this programme — no account,
no funding, no credentials — whereas Alpaca (S-1) and Saxo (S-6) can. That
single line, if it survives verification, decides the ranking. It is a search
summary. It is not verified. The recommendation in §5 is explicitly conditional
on it.

---

## 4. Weighted decision matrix

Weights are set by what this programme actually needs next, and they are stated
before the scores so the ranking cannot be reverse-engineered from a preferred
answer.

| Criterion | Weight | Why this weight |
|---|---:|---|
| Reachable without funding, ID or a live account | 30% | The programme's hard constraint. A broker that cannot be evaluated without opening a funded account cannot be evaluated at all right now. |
| Clean paper/live separation | 25% | M084's whole safety boundary is that submission is impossible. The next milestone's boundary will be that submission cannot reach live. A separation that is one boolean away is worth less than one that is a different credential entirely. |
| API surface verifiable from an official source | 20% | An interface chosen from documentation nobody could open is a guess. |
| Real-time data available at the evaluation tier | 15% | M084 refuses non-real-time feeds outright (`MARKET_DATA_NOT_REAL_TIME`), so a target with no real-time tier cannot exercise the product at all. |
| Licence and operational terms | 10% | Proprietary licences are the Owner's decision, not an implementation detail. |

Scores are 1–5. A criterion scored from an `UNVERIFIED-SECONDARY` row is marked
`†` and carries the tier with it.

| Criterion | Weight | Alpaca | IBKR | Saxo |
|---|---:|---:|---:|---:|
| Reachable without funding/ID | 30% | 5 † | 1 † | 4 † |
| Paper/live separation | 25% | 3 | 4 † | 4 † |
| Surface verifiable from official source | 20% | 5 | 2 | 1 |
| Real-time data at evaluation tier | 15% | 3 † | 2 † | 2 † |
| Licence and terms | 10% | 4 | 2 | 3 |
| **Weighted total** | | **4.15** | **2.10** | **3.05** |

Two scores deserve their reasoning stated rather than left in a cell:

- **Alpaca's paper/live separation scores 3, not 5**, despite being the
  preferred target. `TradingClient(paper=True)` versus `paper=False` is one
  boolean between simulated and real money, verified in their own source. That
  is a genuine hazard for any future milestone, and pretending otherwise to
  tidy the table would be exactly the kind of comfortable reporting this
  campaign exists to avoid. It is carried into §7 as a design requirement.
- **IBKR scores 2 on verifiability** rather than 1: its package identity was
  confirmed primary on PyPI even though its API documentation was blocked.

---

## 5. Conclusion

**Preferred target: Alpaca — CONDITIONAL, pending §6.**
**Fallback: Saxo Bank SIM.**
**Not selected for the next step: Interactive Brokers.**

Alpaca leads on the only criterion that is currently binding: it appears to be
reachable for evaluation without funding, identity verification or a live
account (S-1), and it is the only one of the three whose order surface this
session could read from the vendor's own published source. Saxo is the fallback
because S-6 suggests the same reachability but no official surface was
verifiable. IBKR is not selected *for the next step only*, on the strength of
S-4; it is a serious platform, and if S-4 turns out to be wrong or to have
changed, this ranking should be redone rather than defended.

**This conclusion is conditional and must not be treated as settled.** Its
decisive input is a search summary, and the difference between first and third
place rests on it. If §6 refutes S-1 or S-4, the ranking changes.

---

## 6. Operator verification checklist

Each row is a page this environment could not open and the exact question to
answer on it. Record the answer, the date and the page's own wording — a
retrieved page can be quoted; a summary of one cannot.

| # | Open this URL | Answer exactly this | Confirms / refutes |
|---|---|---|---|
| V-1 | `https://docs.alpaca.markets/us/docs/paper-trading` | Can a paper-only account be created with an email address alone — no funding, no minimum, no government ID? Quote the sentence. | S-1 |
| V-2 | `https://alpaca.markets/support/requirements-alpaca-brokerage-account` | Which countries may open a **paper-only** account, as distinct from a live one? | S-1 |
| V-3 | `https://docs.alpaca.markets/us/docs/about-market-data-api` | Which real-time feed does the free tier provide, and what does SIP cost per month? | S-3 |
| V-4 | `https://docs.alpaca.markets/us/docs/paper-trading` | Is the paper API key **distinct** from the live key, or does the same credential reach both with only the base URL differing? | §7 hazard |
| V-5 | `https://www.interactivebrokers.com/campus/trading-lessons/request-paper-trading-account/` | Is an **approved and funded** live account a prerequisite for a paper account? Quote it. | S-4 — the pivotal claim |
| V-6 | `https://www.interactivebrokers.com/en/pricing/market-data-pricing.php` | What is the monthly cost of the minimum US equities real-time subscription? | S-5 |
| V-7 | `https://interactivebrokers.github.io/tws-api/` | Confirm the order-submission entry point and the supported order types and TIF values. | §2.2 gap |
| V-8 | `https://www.developer.saxo/accounts/sim/signup` | Can a SIM developer account be created free, with no live Saxo relationship? | S-6 |
| V-9 | `https://www.developer.saxo/openapi/learn/environments` | Exactly which market data is unavailable in SIM, and is the SIM token separate from any live credential? | S-7 |
| V-10 | IB API licence text | Does the non-commercial licence permit this programme's intended use? | §2.2 |

Until V-1 and V-5 are answered from the pages themselves, §5 stays
**CONDITIONAL** and this document is not a basis for choosing a broker.

---

## 7. Requirements this research places on any future milestone

Recorded here because they were learned here. They bind a future milestone;
they are not started, and none of them is authorized by this document.

1. **The live path must be unreachable, not merely unselected.** Alpaca's own
   client separates simulated from real money with `paper=True`. A boolean is a
   typo away from being wrong. A future milestone must make live submission
   impossible by construction — a credential that cannot reach it, or a
   deny-list on the live host — in the way M084 makes *all* submission
   impossible today.
2. **A submission state must be added in the open.** M084's `SubmissionState`
   has exactly one member and the database CHECK pins it there. Adding a second
   is a visible schema and domain change that cannot be slipped in, and mutation
   families 19 and 25 fail if either closure is weakened.
3. **The deny-list must be narrowed deliberately, never relaxed.** `alpaca` is
   currently blocked for every module. Permitting it anywhere is a decision to
   be made once, explicitly, for one named module — not a line quietly removed
   from a list.
4. **Real-time entitlement must be confirmed before, not after.** M084 refuses
   `MARKET_DATA_NOT_REAL_TIME` outright. If the evaluation tier yields only
   delayed or partial-venue data, every evaluation returns NO_TRADE and the
   milestone proves nothing.
5. **This document does not authorize contact.** Opening an account, accepting
   terms, creating a credential or subscribing to data are Owner decisions,
   each taken separately, none of them implied by a ranking.
