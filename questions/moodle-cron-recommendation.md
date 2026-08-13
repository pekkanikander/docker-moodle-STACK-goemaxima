# Moodle Cron Best Practice (Internet Needed)

Context: We run Moodle 5.1 in Docker (OrbStack on macOS) with a custom image.
We’re deciding how to run `admin/cli/cron.php` (host scheduler vs sidecar container vs in-container cron).

Please answer with sources/links and concrete guidance.

## Questions to answer
1) For Moodle 5.1, what is the recommended way to run cron in containerized deployments?
2) Is a separate “cron” container (same image, loop or crond) considered good practice?
3) What concurrency/locking behavior does Moodle use to avoid overlapping cron runs?
4) Any official docs or community best practices for Docker/Compose setups?

## Final output format requested
- Summary recommendation
- Evidence/links
- Example implementation (if applicable)

---

## Answers

### Summary recommendation
For Moodle 5.1 in Docker/Compose:
- **Run `admin/cli/cron.php` every minute** (Moodle’s recommendation). citeturn3view0
- Prefer a **single, explicit “cron runner”** (one scheduler + one command) rather than embedding a full cron daemon inside the main web/PHP container.
  - In local dev on macOS/OrbStack: `launchd` user agent running `docker compose exec -T webserver php admin/cli/cron.php` every minute is the cleanest.
  - In “container orchestration” contexts: use the orchestrator’s native scheduler (Kubernetes `CronJob`, Nomad periodic job, etc.) to run the same CLI command.
- A **separate cron container** (same Moodle image or a minimal PHP image mounting the same code + moodledata) is widely used and fine, as long as it is the *only* place you schedule the run (unless you intentionally scale cron with multiple processes).

### Evidence / official guidance
#### Moodle official docs
- Moodle cron is required and Moodle recommends **running it every minute**; CLI script is the preferred method. citeturn3view0
- Moodle docs explicitly describe clustered scenarios: cron can be **triggered from multiple web servers** and Moodle uses **locking to prevent tasks running concurrently**. citeturn4view0
- Moodle docs describe deliberate scaling by running **multiple cron processes** and also separate ad-hoc task processors; default concurrency limits are described and configurable. citeturn4view0

#### Moodle locking / overlap prevention
- Moodle’s Lock API documentation explicitly calls out cron as the “prime candidate” and describes locking to prevent conflicting work across processes. citeturn1search7turn0search5

### 1) For Moodle 5.1, what is the recommended way to run cron in containerised deployments?
Moodle does not mandate a “container-specific” mechanism; the recommendation is still: **run the CLI cron script every minute**. citeturn3view0turn4view0

In containerised deployments, the industry-standard mapping is:
- **Schedule outside the web container** (host scheduler, or orchestrator scheduler) and invoke `php admin/cli/cron.php` inside the running container.
- Alternatively, have a **dedicated cron-runner container** whose only job is to execute `php admin/cli/cron.php` on a schedule.

The key is that you always end up executing the same Moodle-supported entrypoint: `admin/cli/cron.php`. citeturn3view0

### 2) Is a separate “cron” container (same image, loop or crond) considered good practice?
Yes, it’s a common and defensible pattern in Compose-style deployments:
- It keeps the web container single-purpose.
- It makes scheduling explicit and testable.

Caveats:
- Avoid a naive `while true; do ...; sleep 60; done` loop if you care about drift; prefer an actual scheduler (host `cron`/`launchd`, Kubernetes `CronJob`, etc.).
- If you do run `crond` in a container, you now have “process supervision” concerns (logging, PID 1 semantics, etc.). That’s often fine in dev, but it’s extra machinery.

(There are many community Compose examples that include a dedicated `cron` service container for Moodle.) citeturn1search8turn1search4turn0search3

### 3) What concurrency/locking behaviour does Moodle use to avoid overlapping cron runs?
Two layers matter:

1) **Task-level locking (core behaviour):** Moodle uses locks so that tasks don’t execute concurrently in conflicting ways, and this is explicitly designed to support multiple cron triggers (e.g. multiple web servers) without duplicating task execution. citeturn4view0turn1search7turn0search5

2) **Configurable parallelism:** Moodle can be scaled by running multiple cron processes and by running dedicated ad-hoc processors. The docs describe defaults and how to increase concurrency. citeturn4view0

Concrete knobs (from the Cron docs):
- Default **scheduled task** and **ad-hoc task** concurrency limits are 3 each, configurable via the UI (Task processing) or in `config.php` (e.g. `$CFG->task_scheduled_concurrency_limit`). citeturn4view0

Operational implication:
- If your scheduler triggers cron every minute and a previous run is still going, Moodle’s locking/concurrency system is the primary guardrail. Don’t “double-lock” unless you have a specific reason.

### 4) Official docs or community best practices for Docker/Compose setups?
Official Moodle guidance you can treat as normative:
- Use **CLI cron** and run it **every minute**. citeturn3view0
- Locking is built-in and the system supports both clustered and scaled cron patterns. citeturn4view0turn1search7

Community practice in Compose deployments:
- Either a host/orchestrator scheduler that executes into the web container, or a dedicated `cron` service container. Both patterns are widely used; the dedicated-container approach is common in “all-in-Compose” examples. citeturn0search3turn1search8

## Example implementation
### A) macOS (OrbStack) + `launchd` user agent (recommended for local dev)
Run every minute:
```sh
cd /path/to/compose/project \
  && docker compose exec -T webserver php admin/cli/cron.php
```

Minimal `~/Library/LaunchAgents/dev.moodle.cron.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>dev.moodle.cron</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>-lc</string>
    <string>cd /path/to/compose/project &amp;&amp; docker compose exec -T webserver php admin/cli/cron.php</string>
  </array>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/moodle-cron.out</string>
  <key>StandardErrorPath</key><string>/tmp/moodle-cron.err</string>
</dict>
</plist>
```

### B) Compose sidecar `cron` service (works, but more moving parts)
Sketch:
```yaml
services:
  webserver:
    # your existing Moodle/PHP service

  cron:
    image: alpine:3.20
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    entrypoint: ["/bin/sh","-lc"]
    command: |
      apk add --no-cache docker-cli busybox-suid
      echo '* * * * * docker exec -t YOUR_WEBSERVER_CONTAINER php admin/cli/cron.php >/proc/1/fd/1 2>/proc/1/fd/2' > /etc/crontabs/root
      crond -f -l 2
```
Notes:
- You must set `YOUR_WEBSERVER_CONTAINER` correctly (Compose container names can be `project-webserver-1`).
- Mounting the Docker socket grants broad control to that container (acceptable for local dev; be explicit if you ever copy this pattern elsewhere).

## Evidence / links
- MoodleDocs “Cron” (run every minute; clustered/scaled cron guidance; concurrency knobs): citeturn4view0turn3view0
- Moodle Dev Docs “Lock API” (cron as prime locking candidate): citeturn1search7turn0search5
- Community Compose examples with dedicated cron container: citeturn0search3turn1search8turn1search4
