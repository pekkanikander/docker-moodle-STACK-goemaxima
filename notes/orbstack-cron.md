# OrbStack Cron Support (Internet Needed)

Context: We run Moodle in Docker containers under OrbStack on macOS. Moodle requires
`admin/cli/cron.php` to run every minute. We want a lightweight, reproducible approach
for local development using OrbStack.

Please answer with sources/links and concise guidance.

## Questions to answer
1) Does OrbStack support running cron inside containers in a standard way?
2) Are there OrbStack-specific recommendations (e.g., using a sidecar cron container,
   host-level cron invoking `docker compose exec`, or OrbStack features)?
3) If there is a recommended pattern, provide an example command or Compose snippet.
4) Any caveats or pitfalls specific to OrbStack on macOS?

## Final output format requested
- Summary recommendation
- Evidence/links
- Example implementation (if applicable)

---

## Answers

### Summary recommendation
- OrbStack does not provide a special “cron-in-containers” feature; treat it as a standard Docker Engine environment.
- For local development, prefer a **host-scheduled** trigger (macOS `launchd`) that runs `docker compose exec -T ... php admin/cli/cron.php` every minute.
- If you want everything self-contained in Compose, use a **sidecar “cron” service** (e.g., Alpine/busybox) that runs `crond` and executes `docker exec` into the Moodle container, but this is usually more brittle than host scheduling.

### 1) Does OrbStack support running cron inside containers in a standard way?
Yes—indirectly, because OrbStack provides a Docker Engine and runs ordinary containers. If you install and run `cron`/`crond` in a container, it works the same way it would under Docker Desktop/Linux.

Evidence:
- OrbStack docs: it “includes a Docker engine to run containers” and standard container features work as expected. citeturn0search0
- OrbStack docs: it bundles up-to-date Docker CLI tools including Compose. citeturn1search9

Practical note: cron is not “magically present” in most images; you must install it, run it in the foreground (or under a supervisor), and ensure logs go somewhere you can see.

### 2) OrbStack-specific recommendations / patterns?
OrbStack-specific guidance is mainly about **startup and lifecycle** rather than cron itself:
- OrbStack runs in a **user context** on macOS; headless/boot-time automation is constrained because it can’t be launched as a root LaunchDaemon in the usual way. citeturn1search4

Given that constraint, the two workable patterns are:
1) **macOS `launchd` user agent** runs the cron trigger (best for local dev).
2) **Sidecar cron container** inside the Compose project (works if your project is up and OrbStack is running, but adds another moving part).

### 3) Recommended pattern + example

#### Option A (recommended): host-level schedule via `launchd` (user agent)
This keeps the Moodle/PHP container single-purpose and avoids “cron-daemon-in-a-container” complexity (a common recommendation in container discussions). citeturn0search3turn0search20

Command you want `launchd` to run every minute:
```sh
cd /path/to/your/compose/project \
  && docker compose exec -T moodle php admin/cli/cron.php
```

Minimal `~/Library/LaunchAgents/dev.moodle.cron.plist` example:
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
    <string>docker compose --project-directory /path/to/your/compose/project exec -T moodle php admin/cli/cron.php</string>
  </array>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/moodle-cron.out</string>
  <key>StandardErrorPath</key><string>/tmp/moodle-cron.err</string>
</dict>
</plist>
```
Load/unload:
```sh
launchctl load -w ~/Library/LaunchAgents/dev.moodle.cron.plist
launchctl unload -w ~/Library/LaunchAgents/dev.moodle.cron.plist
```

#### Option B: sidecar cron service in Compose
This is “self-contained”, but you must:
- ensure the sidecar has `crond` installed,
- ensure the sidecar can call Docker (usually by mounting the Docker socket),
- handle permissions and the fact that `docker exec` targets a container name.

Example (sketch):
```yaml
services:
  moodle:
    # ... your existing moodle service

  cron:
    image: alpine:3.20
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    entrypoint: ["/bin/sh","-lc"]
    command: |
      apk add --no-cache docker-cli busybox-suid
      echo '* * * * * docker exec -t moodle php admin/cli/cron.php >/proc/1/fd/1 2>/proc/1/fd/2' > /etc/crontabs/root
      crond -f -l 2
```
This is intentionally a sketch because container naming (`moodle` vs `project-moodle-1`) and socket access vary.

### 4) Caveats / pitfalls specific to OrbStack on macOS
- **OrbStack must be running** for any of this to work. On headless machines or after reboot without login, this may be the limiting factor (OrbStack runs in user context). citeturn1search4
- `docker compose exec` from schedulers should generally use `-T` to avoid TTY allocation issues.
- If you use a sidecar that mounts the Docker socket, you are effectively giving that container broad control over your local Docker environment (fine for dev, but be explicit about it).
- If your bind mounts sit on the macOS filesystem, file watching and performance characteristics can differ from Linux; cron itself isn’t affected, but debugging “why didn’t cron do X?” sometimes is.

## Evidence / links
- OrbStack Docker containers docs (OrbStack provides a Docker engine): citeturn0search0
- OrbStack Docker docs (bundled CLI tools incl. Compose): citeturn1search9
- OrbStack issue: OrbStack requires user context; headless auto-start constraints: citeturn1search4
- Discussion: prefer host scheduling rather than cron inside containers: citeturn0search3turn0search20
