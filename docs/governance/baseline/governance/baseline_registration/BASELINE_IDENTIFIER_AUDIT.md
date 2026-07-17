# BASELINE_IDENTIFIER_AUDIT

Registration timestamp: 2026-07-12T23:29:29+03:00

Purpose: identifier continuity audit for mandatory namespaces.

| Namespace | Current Evidence | Gaps | Duplicates / Collisions | Orphan References | Audit Result |
|---|---|---|---|---|---|
| RES | Loaded files reference RES-0001 and RES-0029 through RES-0043; registry claims current range through RES-0043 | RES-0002 through RES-0028 not file-verified | No allocation collision detected in loaded files | Early RES references depend on missing baselines | PENDING |
| DEC | Loaded files reference DEC-0001, DEC-0002, DEC-0005, DEC-0031, DEC-0033 through DEC-0043 | Most DEC-0003 through DEC-0032 not file-verified | No allocation collision detected in loaded files | Early DEC references depend on missing baselines | PENDING |
| SRC | Loaded files reference SRC-0001 and SRC-0015 through SRC-0031 | SRC-0002 through SRC-0014 not file-verified | No allocation collision detected in loaded files | SRC-0001 and other early sources depend on missing baselines | PENDING |
| ASS | Loaded files reference ASS-0001, ASS-0002, ASS-0009 through ASS-0013 | ASS-0003 through ASS-0008 not file-verified | No allocation collision detected in loaded files | Early assumptions depend on missing baselines | PENDING |
| CONF | Loaded files reference CONF-0001 | None detected after CONF-0001 | No collision detected | CONF-0001 unresolved in source materials | PENDING |
| CLM | Loaded files reference CLM-0001 through CLM-0057 | No internal gap detected in loaded Phase 2 claim range | No allocation collision detected in loaded files | None detected in loaded claim range | VERIFIED FOR LOADED FILES |
| RISK | Master Risk Register imports RISK-0001 through RISK-0034 | No internal gap detected | No allocation collision detected in loaded risk register | Upstream risk history before loaded files not independently verified | VERIFIED FOR LOADED FILES |
| DEF | Master Deferred Item Register imports DEF-0001 through DEF-0008 | No internal gap detected | No allocation collision detected | No orphan DEF detected in loaded protocol/register | VERIFIED FOR LOADED FILES |
| CAMP | CAMP-0001 appears in proposal and review; Identifier Registry still says CAMP reserved, none allocated | Registry not synchronized with CAMP-0001 | Potential registry/proposal conflict, not numeric collision | CAMP-0001 orphaned from identifier registry | BLOCKED |
| RUN | RUN-0001 appears as reserved/example only | No active RUN allocation | No collision detected | No active run registry exists | NOT ACTIVE |
| EVID | EVID-0001 appears as reserved/example only | No active EVID allocation | No collision detected | No active evidence package exists | NOT ACTIVE |
| REVIEW | REVIEW-0001 appears in authorization review; Identifier Registry says REVIEW reserved, none allocated | Registry not synchronized with REVIEW-0001 | Potential registry/review conflict, not numeric collision | REVIEW-0001 orphaned from identifier registry | BLOCKED |
| AUD | AUD-0001 appears as reserved/example only | No active AUD allocation | No collision detected | No active audit registry exists | NOT ACTIVE |
| DCAND | DCAND-0001 appears as reserved/example only | No active DCAND allocation | No collision detected | No active decision-candidate registry exists | NOT ACTIVE |

Identifier conclusion: loaded Phase 2, risk, deferred, and claim ranges are internally coherent, but full identifier continuity cannot be certified until missing 000A through 000B.4 Phase 1 baselines are registered. CAMP-0001 and REVIEW-0001 require synchronization into the Master Identifier Registry.
