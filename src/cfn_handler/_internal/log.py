"""Internal logger setup.

We expose a logger named ``cfn_handler`` and never attach handlers, formatters,
or filters by default. Log configuration is the user's responsibility — this
matches the Python library logging convention and avoids surprising the user's
chosen logging stack (e.g. AWS Lambda Powertools, structlog, plain stdlib).
"""

from __future__ import annotations

import logging

#: The logger used throughout the library. Use ``logger.getChild("subname")``
#: in submodules to namespace records.
logger = logging.getLogger("cfn_handler")
"""Module-level logger; never has handlers attached by the library."""
