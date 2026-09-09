"""MILESTONE-084 configuration validation CLI.

Reads a configuration file and reports whether this product would accept it --
WITHOUT storing anything and WITHOUT touching the database at all. That is the
point: an operator editing policy should be able to check the file before it
becomes a version, and a check that required a working database would be
unavailable exactly when a misconfiguration is most likely.

Exit code 0 means the file would be accepted; 1 means it would be refused, with
the reason on stderr. The reason is the domain type's own refusal, not a
paraphrase, so what the operator reads here is what would have happened.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    load_json_file,
    read_configuration,
    render_configuration_json,
)

_USAGE = "usage: empirical-platform-validate-trading-configuration [--json] <configuration.json>"


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    try:
        configuration = read_configuration(load_json_file(positional[0]))
    except (InputError, ValueError) as error:
        if as_json:
            print(json.dumps({"valid": False, "reason": str(error)}, sort_keys=True))
        else:
            print(f"REFUSED: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    if as_json:
        print(
            json.dumps(
                {"valid": True, "configuration": render_configuration_json(configuration)},
                sort_keys=True,
            )
        )
    else:
        print(
            f"ACCEPTED: {configuration.configuration_governance_id} "
            f"v{configuration.configuration_version} would be stored as written. "
            "Nothing was written."
        )


main = operator_command(_main)


if __name__ == "__main__":
    main()
