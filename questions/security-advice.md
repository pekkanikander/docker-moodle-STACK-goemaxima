# MARIADB security advice

# MariaDB security advice (Docker Compose, local-only network)

## Context and threat model

This project assumes:
- A **local Docker Compose network** (Moodle + MariaDB).
- **No host-external exposure** of the database (no published DB ports).
- Primary risks are **accidental credential leakage**, **container compromise**, and **operational mistakes**, not hostile remote attackers.

The goal is therefore **damage limitation and hygiene**, not absolute secrecy from a root-equivalent operator.

---

## Recommended community practice (as of ~2026)

### 1. Do not expose MariaDB outside Docker
- Do **not** use `ports:` for the MariaDB service.
- Rely on the internal Compose network only.
- Optionally restrict `MARIADB_ROOT_HOST=localhost` if compatible with your setup.

This eliminates the largest attack surface.

---

### 2. Use a dedicated database user for Moodle
- Create a database (e.g. `moodle`) and a user (e.g. `moodle`).
- Grant only the required privileges for that database.
- **Do not** use the MariaDB root account for Moodle.

Least privilege limits the impact of a Moodle-side compromise.

---

### 3. Prefer Docker *secrets* over plaintext environment variables

**Best practice:**
- Store credentials as **files**, mounted into containers via Docker Compose `secrets`.
- Use MariaDB’s native `*_FILE` environment variable support.

Example pattern:
- Secrets live on the host (not in git), e.g.:
  - `secrets/mariadb_root_password.txt`
  - `secrets/moodle_db_password.txt`
- Secrets are mounted at runtime under `/run/secrets/...`.

MariaDB officially supports:
- `MARIADB_ROOT_PASSWORD_FILE`
- `MARIADB_PASSWORD_FILE`

This avoids:
- committing passwords into `compose.yaml`,
- accidental exposure via `docker inspect`,
- casual leakage through logs or screenshots.

---

### 4. Generate secrets at *deploy time*, not at build time

**Do NOT generate passwords at image build time.**

Reasons:
- Build-time secrets risk being baked into image layers.
- Rebuilding images would rotate passwords unexpectedly.
- Persistent DB volumes would become unusable.

**Correct pattern:**
- Generate strong random secrets **once**, outside the image.
- Store them as files (permissions ~0600).
- Reuse them across container restarts and upgrades.

This aligns with Docker’s secrets model and with persistent volumes.

---

### 5. Avoid `MARIADB_RANDOM_ROOT_PASSWORD` for persistent setups

While MariaDB can auto-generate a root password, it:
- prints the generated password to container logs,
- complicates controlled backup/restore workflows.

For long-lived databases, a pre-generated secret file is preferable.

---

### 6. Moodle images and secrets: practical note

- Some Moodle images support `*_FILE` variables directly.
- If not, use a **small entrypoint wrapper** that:
  - reads the secret file,
  - exports the expected environment variable,
  - then starts Moodle.

This still keeps secrets out of `compose.yaml` and version control.

---

## Acceptable minimal fallback (local-only setups)

If Docker secrets feel too heavy:
- Use a `.env` file **not committed to git**.
- Lock file permissions tightly.
- Interpolate variables into `compose.yaml`.

This is common in local stacks, but secrets are still preferred when available.

---

## Summary

**Recommended default for this project:**
- No DB port exposure.
- Dedicated Moodle DB user.
- Credentials stored as host-generated secrets.
- Secrets injected at runtime via Docker Compose.
- No build-time password generation.

This strikes a pragmatic balance between security, reproducibility, and operational simplicity.
