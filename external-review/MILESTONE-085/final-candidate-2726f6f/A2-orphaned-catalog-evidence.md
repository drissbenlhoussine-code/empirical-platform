# A2 evidence: orphaned pg_proc rows in disposable database m085_pgon_53f878c (2026-09-26)

Observed with a diagnostic copy of `_catalog` (scratch plugin probe_catalog.py) on the SAME
connection/transaction as the failing test, before the database was recreated:

paper_execution_attempt_guard_update: 2 rows
  {'oid': 6515131, 'ns': '6514009', 'xmin': '2238170', 'args': '', 'src': '\nDECLARE\n    allowed text[];\nBEGIN\n    -'}
  {'oid': 7221131, 'ns': 'public',  'xmin': '2264086', 'args': '', 'src': '\nDECLARE\n    allowed text[];\nBEGIN\n    -'}
paper_execution_authorization_guard_update: 2 rows
  {'oid': 6515126, 'ns': '6514009', 'xmin': '2238170', 'args': '', 'src': '\nBEGIN\n    -- Consumption is the ONLY pe'}
  {'oid': 7221126, 'ns': 'public',  'xmin': '2264086', 'args': '', 'src': '\nBEGIN\n    -- Consumption is the ONLY pe'}
other sessions on the database at that instant: []

`pronamespace = 6514009` had NO row in pg_namespace (regnamespace rendered the bare OID), i.e.
the rows were orphaned when their schema was dropped; a query joining pg_namespace (the first
probe) therefore did not show them, while the tests' unqualified
`SELECT prosrc FROM pg_proc WHERE proname = :name` returned two rows -> MultipleResultsFound.
Orphan count per database before recreation (pg_proc rows whose namespace does not exist):
m085_pgon_53f878c = 2 (min pronamespace 6514009, min xmin 2238170); m085_pgon_c7a41f0 = 0;
m085_pgon_b24c471 = 0.  Both orphan xmins (2238170) predate the run; the database had earlier
hosted a pytest process that was killed mid-run (a `TRUNCATE` hang after an unclosed
connection, and the memory-reaper kill of a background chain) while another connection was
executing `DROP SCHEMA public CASCADE` / `CREATE OR REPLACE FUNCTION` sequences.
The mechanism that produced the orphans was NOT demonstrated; only their presence and effect.
No system catalog was modified. The disposable database was dropped and recreated
(`DROP DATABASE` / `CREATE DATABASE ... OWNER empirical_m085_verify`); the two round-trip tests
then passed (R3b: 423 passed), and pass in isolation and in R1 on a clean database.
