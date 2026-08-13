# Internet Research Questions

Context: We are building an OSS Docker Compose setup for Moodle + MariaDB + goemaxima (STACK).
We need 2026-era best-practice guidance with pinned versions and reproducible CI.

Please answer with sources/links and concise conclusions.

## 1) Moodle Docker image choice (official vs Bitnami vs others)
- What is the recommended Docker image source for Moodle as of 2026?
- Is there an "official" Moodle image (maintained by Moodle HQ or Docker Official Images)?
- If Bitnami is outdated, what is the recommended alternative and why?
- Any known caveats with the leading image choices (updates, security, PHP versions, plugin installs)?

## 2) Recommended version line
- Which Moodle major/minor line should we target first (prefer LTS if applicable)?
- Which PHP and MariaDB versions are considered compatible for that line?

## 3) STACK + goemaxima compatibility
- What STACK version is recommended for the target Moodle line?
- What goemaxima tag/version is recommended for that STACK version?
- Are there known compatibility pitfalls between STACK and goemaxima?

## 4) goemaxima endpoint defaults
- What is the standard goemaxima HTTP endpoint URL (host/port/path) used by STACK?
- Any required health endpoint or path for testing connectivity?

## 5) Automated STACK installation in Docker
- What is the most reliable fully-automated method to install STACK in a containerized Moodle instance?
- Is Moodle CLI plugin install stable for STACK, or is mounting the plugin directory preferred?
- Any required companion plugins or configuration steps?


---

# Answers (internet research; updated 2026-01-02)

## 1) Moodle Docker image choice (official vs Bitnami vs others)

### Is there an “official” Moodle image?
- There is **no Docker Official Image** for Moodle LMS itself (i.e. no `library/moodle` maintained as a Docker Official Image).
- Moodle HQ maintains **developer/test-focused images** and tooling:
  - `moodlehq/moodle-php-apache` (PHP+Apache environment for Moodle, based on Official PHP images) — primarily a dev/test building block rather than a full “Moodle-in-a-box” production image. https://hub.docker.com/r/moodlehq/moodle-php-apache
  - `moodlehq/moodle-docker` is explicitly a **developer/test environment** (“aimed at Moodle developers and testers”). https://github.com/moodlehq/moodle-docker
  - Several MoodleHQ DB images explicitly note they’re **not intended for production use** (development/testing/CI). Example: https://hub.docker.com/r/moodlehq/moodle-db-oracle-r2

### Recommended approach for production-ish Docker
Given the above, the most reproducible and maintainable pattern (and the one that keeps you closest to “upstream”) is:
1. **Build your own Moodle runtime image** pinned by:
   - a base image digest (`php:<version>-apache` or similar), and
   - an explicit Moodle release tarball/zip (or git tag) checksum.
2. Keep **Moodle code read-only** at runtime (except when upgrading) and keep all writable state outside:
   - `moodledata` (volume)
   - DB (volume/service)
   - any caches you want to persist

This is consistent with Moodle’s general guidance that production installs should not have the web server writing into the code tree (and aligns with the hardening advice often given in forum discussions about production Docker setups).

### Bitnami: still viable, but understand the trade
- Bitnami’s `bitnami/moodle` container exists and is actively used, but Bitnami itself recommends Helm for production deployments and also emphasises immutable tags for production. https://hub.docker.com/r/bitnami/moodle
- There is community concern about maintenance/long-term viability of the Bitnami Moodle image (discussion thread). https://moodle.org/mod/forum/discuss.php?d=469337

Practical conclusion for this OSS Compose repo:
- For a learning/prototyping repo, Bitnami is convenient.
- For a repo that aims at **pinned, reproducible CI and long-term confidence**, prefer a **small, explicit “build-your-own” Moodle image** which pulls Moodle from official releases and pins everything.

## 2) Recommended version line

### Which Moodle line?
Two sensible targets (pick based on your churn tolerance):

**Option A (stability / longest security runway): Moodle 4.5 LTS**
- Moodle 4.5 is an LTS release. General (bugfix) support ended 6 Oct 2025; security support ends 4 Oct 2027. https://moodledev.io/docs/4.5
- Release schedule and support windows: https://moodledev.io/general/releases

**Option B (newer platform / more ongoing bugfixes “now”): latest supported major**
- If you want fewer backports and more “current” behaviour, target the latest fully supported major at the time you pin the repo, and update it on your own schedule.

Given this and the project goals, Option B seems better, if feasible w.r.t STACK + goemaxima.

### PHP and MariaDB compatibility
For **Moodle 4.5 (LTS)**:
- PHP: 8.1 to 8.3 (per MoodleDocs “PHP” matrix). https://docs.moodle.org/en/PHP
- MariaDB: minimum 10.6.7 (per Moodle 4.5 release requirements). https://moodledev.io/general/releases/4.5

For **Moodle 5.0 (as an example of the newer line)**:
- Moodle downloads list current requirements (example page shows: PHP 8.2; MariaDB 10.11.0+ or MySQL 8.4 or Postgres 14, etc.). https://download.moodle.org/releases/supported/

## 3) STACK + goemaxima compatibility

### STACK version recommendation
- STACK publishes a mapping of STACK plugin version numbers to release names and supported Maxima versions: https://moodle.oulu.fi/question/type/stack/doc/doc.php/Installation/STACK_versions.md
- Installation docs note STACK has been tested on Moodle 4.0 to 4.5 inclusive (and intends to support new Moodle releases, but may lag on explicit testing statements). https://moodle.oulu.fi/question/type/stack/doc/doc.php/Installation/index.md

Practical recommendation:
- Use the **latest stable STACK release** that is listed as compatible with your chosen Moodle line.
- Use STACK’s `STACK_versions.md` to pin:
  - the plugin version number (e.g. `2025xxxx00` style),
  - the supported Maxima versions.

### goemaxima tag/version recommendation
- STACK’s installation docs explicitly say you **must match the goemaxima version to the same version of the STACK plugin**. https://moodle.oulu.fi/question/type/stack/doc/doc.php/Installation/index.md
- goemaxima’s README explains that the container images are tagged by `STACKMAXIMA_VERSION` and provides the URL path that STACK should use. It also includes a mapping table. https://github.com/mathinstitut/goemaxima

Practical recommendation:
- Pin **both**:
  1) the STACK plugin version (from Moodle plugins directory / your vendored zip), and
  2) the matching `STACKMAXIMA_VERSION` / goemaxima image tag.

### Known pitfalls
- Ensure Moodle PHP has `mbstring` enabled; STACK v4.3+ requires it. https://moodle.oulu.fi/question/type/stack/doc/doc.php/Installation/index.md
- Ensure your Maxima version is one of STACK’s supported versions (recent docs recommend Maxima >= 5.43.0, and list a supported range). https://moodle.oulu.fi/question/type/stack/doc/doc.php/Installation/index.md

## 4) goemaxima endpoint defaults

From goemaxima’s README:
- Container listens on **port 8080**.
- The STACK CAS URL should be:
  - `http://<host>:<port>/goemaxima`
  - Older images accept only `.../maxima` but the README notes this should still work in newer versions too. https://github.com/mathinstitut/goemaxima

Health endpoint:
- I did not find a documented dedicated `/health` endpoint in the primary goemaxima README. The simplest connectivity test is to use STACK’s own connection test / CAS health checks within Moodle once the URL is configured.

## 5) Automated STACK installation in Docker

There are two approaches, both reproducible; pick based on how “immutable” you want containers to be.

### Approach A: Vendor plugins into the image (most reproducible)
- Bake STACK (and any companion plugins you require) into the Moodle image at build time:
  - copy `question/type/stack` into the correct location,
  - run `php admin/cli/upgrade.php --non-interactive` during image build or first container start,
  - keep the Moodle code tree read-only at runtime.
- MoodleDocs documents manual server-side placement of plugins by directory type (STACK is a question type: `question/type/`). https://docs.moodle.org/en/Installing_plugins

### Approach B: Volume-mount plugins + run upgrade on startup (fast iteration)
- Mount the plugin directory into the container, and execute `php admin/cli/upgrade.php` in the entrypoint when you detect the plugin is present but not installed.
- This is a common operational pattern for Moodle (deploy code, then run upgrade/notifications).

Companion plugins / configuration:
- STACK’s own docs should be treated as the source of truth for any required add-ons (MathJax filter configuration, etc.). Start from: https://moodle.oulu.fi/question/type/stack/doc/doc.php/Installation/index.md

Suggested follow-up research tasks (if you want this repo to be very crisp):
- Decide whether you will **vendor STACK zip artifacts** in-repo (with checksums) vs fetch during CI.
- Identify whether STACK’s Moodle plugins directory entry lists any explicit dependencies, and pin those too.
- Decide whether your goemaxima container is on an internal Docker network only (recommended) and how Moodle reaches it.
