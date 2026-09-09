# MILESTONE-084 — Operator Verification Checklist

Facts this milestone could not verify, the exact page that settles each, and
the exact question to ask on it.

This exists because a campaign that quietly rounds "I read a summary of the
page" up to "I checked the page" is worth less than one that admits the
difference. Nothing here is a task for M084; every row is work only a human on
an unrestricted network can do.

---

## Why these could not be verified here

This container's network policy answers `403` to `CONNECT` for all three
brokers' documentation domains. Measured in-session:

```
000  alpaca.markets                      blocked
000  docs.alpaca.markets                 blocked
000  www.interactivebrokers.com          blocked
000  interactivebrokers.github.io        blocked
000  www.developer.saxo                  blocked
000  saxobank.github.io                  blocked
400  github.com                          reachable
301  raw.githubusercontent.com           reachable
200  pypi.org                            reachable
```

What that allowed: reading Alpaca's and IBKR's **own published packages** on
GitHub and PyPI — good primary evidence for API surface. What it did not
allow: anything commercial or contractual, all of which lives only on the
blocked domains.

---

## The checklist

Record, for each row: the date, the answer, and the page's **own wording**. A
page that was opened can be quoted; a summary of one cannot, and the difference
is the entire point of this file.

### Decisive — the recommendation depends on these two

- [ ] **V-1 — Alpaca paper account prerequisites.**
      `https://docs.alpaca.markets/us/docs/paper-trading`
      Can a paper-only account be created with an email address alone: no
      funding, no minimum deposit, no government-issued ID? Quote the sentence.
      *Refuting this removes Alpaca's first-place criterion entirely.*

- [ ] **V-5 — IBKR paper account prerequisites.**
      `https://www.interactivebrokers.com/campus/trading-lessons/request-paper-trading-account/`
      Is an **approved and funded** live account a prerequisite for opening a
      paper trading account? Quote the sentence.
      *This is the single claim that puts IBKR third. If it is wrong or has
      changed, the ranking must be redone, not defended.*

### Material — these change scores but not, on their own, the order

- [ ] **V-2 — Alpaca paper eligibility by country.**
      `https://alpaca.markets/support/requirements-alpaca-brokerage-account`
      Which countries may open a **paper-only** account, as distinct from a
      live one? The two lists are not necessarily the same.

- [ ] **V-3 — Alpaca real-time data tier.**
      `https://docs.alpaca.markets/us/docs/about-market-data-api`
      Which real-time feed does the free tier provide (IEX only?), and what
      does the SIP consolidated feed cost per month?

- [ ] **V-4 — Alpaca credential separation.**
      `https://docs.alpaca.markets/us/docs/paper-trading`
      Is the paper API key a **distinct credential** from the live key, or does
      the same key reach both with only the base URL differing? Alpaca's own
      SDK selects between them with a single `paper=True` boolean, so this
      answer decides how a future milestone must be built.

- [ ] **V-6 — IBKR market data cost.**
      `https://www.interactivebrokers.com/en/pricing/market-data-pricing.php`
      Monthly cost of the minimum US equities real-time subscription, and
      whether a paper user needs it.

- [ ] **V-7 — IBKR API surface.**
      `https://interactivebrokers.github.io/tws-api/`
      The order-submission entry point, the supported order types and the
      time-in-force values. Alpaca's equivalents were read from source; IBKR's
      could not be, and that gap is why IBKR scores 2 rather than 5 on
      verifiability.

- [ ] **V-8 — Saxo SIM signup.**
      `https://www.developer.saxo/accounts/sim/signup`
      Can a SIM developer account be created free, with no existing live Saxo
      relationship?

- [ ] **V-9 — Saxo SIM data and tokens.**
      `https://www.developer.saxo/openapi/learn/environments`
      Exactly which market data is unavailable in SIM, and is the SIM token a
      separate credential from any live one?

- [ ] **V-10 — IB API licence.**
      The IB API Non-Commercial / Commercial licence text.
      Does the non-commercial licence permit this programme's intended use?
      `ibapi` is proprietary, not OSI-licensed. This is an Owner decision.

---

## What must not be done to complete this checklist

The mission's prohibitions apply to every row above. Answering these questions
means **reading public pages**, nothing more:

- do not open an account, paper or live;
- do not accept any terms of service;
- do not create, request or store any credential or API key;
- do not subscribe to any market-data product;
- do not submit any order, paper or live.

A row that cannot be answered from a public page is answered `NOT PUBLIC` and
left for a separate, explicit decision.

---

## Status

**None of the rows above has been completed.** Until V-1 and V-5 are answered
from the pages themselves, the conclusion in `broker-and-market-data-research.md`
§5 remains **CONDITIONAL** and is not a basis for selecting a broker.
