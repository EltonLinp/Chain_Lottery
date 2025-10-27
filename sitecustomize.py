"""Project-wide Python startup customisations."""

import os
from typing import NewType

# Prevent incompatible third-party pytest plugins from auto-loading.
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

# Provide compatibility shim for older pytest plugins expecting eth_typing.ContractName.
try:
    import eth_typing  # type: ignore

    if not hasattr(eth_typing, "ContractName"):  # pragma: no cover
        eth_typing.ContractName = NewType("ContractName", str)  # type: ignore[attr-defined]
    if not hasattr(eth_typing, "ChainId"):  # pragma: no cover
        eth_typing.ChainId = NewType("ChainId", int)  # type: ignore[attr-defined]
except Exception:
    # If eth_typing is not installed yet, ignore; imports later will fail normally.
    pass
