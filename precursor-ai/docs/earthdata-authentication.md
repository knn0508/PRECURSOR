# Earthdata authentication

Searching and discovery are anonymous. **Downloads require NASA Earthdata Login.** The Landslide Catalog import (open data portal) needs no login.

## Setup

1. Create a free account at https://urs.earthdata.nasa.gov/.
2. Provide credentials by **one** of:

```bash
# A) .env at the repo root (never commit it; .env is gitignored)
EARTHDATA_USERNAME=your_user
EARTHDATA_PASSWORD=your_password

# B) ~/.netrc (Windows: %USERPROFILE%\_netrc or .netrc)
machine urs.earthdata.nasa.gov login your_user password your_password
```

On Linux/macOS: `chmod 600 ~/.netrc`.

3. Docker Compose passes `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` from `.env` to the backend container. `~/.netrc` is not mounted into the container; use `.env` there.

If both are present, `.env` credentials are used (via `earthaccess` "environment" strategy); otherwise the `netrc` strategy.

## Handling of secrets

- Settings hold them as `SecretStr`; they are unwrapped only at the `earthaccess` login call.
- Never logged, never stored in PostgreSQL, never returned by the API. Error messages carry the exception type name only, and `scrub()` removes URL query strings and the configured username/password from messages stored in `error_message`.
- `status()` makes no network call and only reports `configured`, `missing` or `failed`. `configured` means credentials are present (or a login already succeeded), not that they are correct. A real login is attempted lazily on the first download. `failed` is set after a rejected login.
- Provenance manifests contain the source URL without its query string and no credentials.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Earthdata credentials missing or invalid" / CLI exit code 4 | Set the variables or the `.netrc` entry above. |
| Download returns 401/403 | Wrong password, **or** the NASA application EULA has not been approved. On your Earthdata profile, approve the applications for the relevant DAAC (GES DISC for IMERG, ASF for NISAR, NSIDC for SMAP; NASADEM is hosted on LP DAAC cloud). This is the most common cause of 403. |
| `failed` after a login attempt | Check username/password; try logging in at https://urs.earthdata.nasa.gov/. |

Not verified: no login has ever been performed against NASA during development; the flow is tested with a mocked login function only.
