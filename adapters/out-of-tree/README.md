# An eighth adapter, living outside the core

AC-2.5 says adding a new adapter *"requires no modification to any core
package"*. This is that, made checkable: a transport that lives in its own
directory, imports nothing from `pact_adapters` except the two type names it
needs to be readable, and is never mentioned anywhere in `src/`.

**It is deliberately not installed.** `adapters/python/pyproject.toml` does not
list it, `pact_adapters` does not import it, and no registry in the core knows
its name. A test puts this directory on `sys.path` the way a separate checkout
would be, and the agent runs.

The criterion also asks for this to be *"proven in CI by building an adapter that
lives in a separate repository"*. This is one directory rather than one
repository, and that shortfall is recorded in
`docs/70-PRODUCTION-GAP-REGISTER.md` rather than papered over: what a separate
directory proves is that no core change is needed, and what a separate repository
would additionally prove is that no core *release* is needed. The second needs
publishing, which is register row C6.
