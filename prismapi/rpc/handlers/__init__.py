"""Import-side-effect registrations for RPC handlers.

Each submodule imported below uses `@rpc("...")` to register its methods.
"""

from prismapi.rpc.handlers import (
    codebooks as _codebooks,
)
from prismapi.rpc.handlers import (
    dedup as _dedup,
)
from prismapi.rpc.handlers import (
    extraction as _extraction,
)
from prismapi.rpc.handlers import (
    fields as _fields,
)
from prismapi.rpc.handlers import (
    identity as _identity,
)
from prismapi.rpc.handlers import (
    members as _members,
)
from prismapi.rpc.handlers import (
    phases as _phases,
)
from prismapi.rpc.handlers import (
    projects as _projects,
)
from prismapi.rpc.handlers import (
    screening as _screening,
)
from prismapi.rpc.handlers import (
    searches as _searches,
)
from prismapi.rpc.handlers import (
    snapshots as _snapshots,
)
from prismapi.rpc.handlers import (
    statefile as _statefile,
)
from prismapi.rpc.handlers import (
    system as _system,
)
from prismapi.rpc.handlers import (
    trash as _trash,
)
