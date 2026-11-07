# Security notes (hackathon MVP)

## Authentication
- Identity = cookie `spr_user`, set from a user-supplied name in `POST /api/login`.
- **This is not authentication.** Anyone who knows a name can impersonate it by
  setting the same cookie value. Acceptable only inside a trusted network.
- For a public server, replace `current_user` in `backend/auth.py` with real auth
  (password, OAuth, signed JWT) and keep the rest of the code intact.

## Ownership
- Every `Config`, `Procedure` and `Run` carries an `owner` / `started_by` field.
- All read/update endpoints call `get_*_owned(...)`. Foreign IDs return **404**
  (not 403) to avoid leaking existence.
- `GET /api/runs` returns only the current user's runs.
- `config_snapshot` in `Run` is immutable — old runs remain reproducible after
  the user edits the config.

## Sandbox
- User code runs in a subprocess with a timeout. It has filesystem and
  environment access of the launching user. Not a hardened sandbox — only for
  trusted users. See `engine/sandbox.py` docstring.