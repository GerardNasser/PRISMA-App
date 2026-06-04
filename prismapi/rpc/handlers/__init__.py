"""Import-side-effect registrations for RPC handlers.

Each submodule imported below uses `@rpc("...")` to register its methods.
"""

from prismapi.rpc.handlers import (  # noqa: F401
    codebooks as _codebooks,
    dedup as _dedup,
    extraction as _extraction,
    fields as _fields,
    identity as _identity,
    members as _members,
    phases as _phases,
    projects as _projects,
    screening as _screening,
    searches as _searches,
    snapshots as _snapshots,
    statefile as _statefile,
    system as _system,
    trash as _trash,
)
