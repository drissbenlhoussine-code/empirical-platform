# Empirical Platform

Foundation scaffold for a governance-aware empirical validation platform.

This repository currently contains only platform scaffolding. It does not implement campaign execution, empirical validation, B3 criteria, vendor adapters, data acquisition, production APIs, UI, Decision Candidates, or Decision Freeze.

## Quick Start

Requires Python `>=3.13,<3.14`.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev,test,security,build]"
.\scripts\verify.ps1
```

## Commands

```powershell
.\scripts\verify.ps1        # full local verification
.\scripts\quality.ps1       # format, lint, type, tests
.\scripts\security.ps1      # dependency audit and secret scan
.\scripts\local-infra.ps1 up
.\scripts\local-infra.ps1 down
```

## Not Implemented

- Business logic.
- Empirical validation.
- Vendor adapters.
- Market-data acquisition.
- B3 criteria.
- Statistical logic.
- Campaign execution.
- Production APIs beyond static health/version placeholders.
- UI.
- Decision Candidate creation.
- Decision Freeze.

