# Version Selection Request (Internet Needed)

Context: We are building a Docker Compose project for Moodle + MariaDB + goemaxima (STACK).
We target the **latest supported Moodle line** (not 4.5 LTS), with a custom Moodle image built from
`php:<version>-apache` and a pinned Moodle release tarball + checksum.
STACK is baked into the image from a pinned plugin ZIP + checksum.
goemaxima runs internally on the Docker network only.

Please answer with sources/links and concrete version choices.

## 1) Moodle (latest supported line or 5.x LTS)
- What is the latest supported Moodle major/minor release line as of now?
- Alternatively, is there a 5.x series LTS release of Moodle?
- Provide the exact release tarball URL and a published SHA256 checksum URL (or source).
- Provide the PHP version range required for this Moodle line.
- Recommend the exact `php:<version>-apache` base tag to use (e.g., 8.x-apache).

## 2) MariaDB compatibility
- Provide a MariaDB version known compatible with the chosen Moodle/PHP line.
- Provide the exact Docker image tag (official MariaDB) to pin.

## 3) STACK plugin
- Provide the latest stable STACK plugin version compatible with the chosen Moodle line.
- Provide the exact Moodle plugins ZIP download URL and a checksum source.
- List any required companion plugins, if any.

## 4) goemaxima
- Provide the goemaxima image tag that matches the STACK plugin version (per official mapping).
- Confirm the default endpoint path (expected: `/goemaxima`, fallback `/maxima`).

## 5) Minimal compatibility tuple
- Summarize a single supported tuple:
  - Moodle version line + release
  - PHP base tag
  - MariaDB tag
  - STACK plugin version + URL + checksum
  - goemaxima tag


---

# Proposed concrete versions (as of 2026-01-02)

## 1) Moodle

### Latest supported major/minor line
- **Moodle 5.1.x** is the current stable line (latest release shown as **5.1.1**). Source: Moodle downloads “Latest release”.

### LTS?
- There is **no “5.x LTS”** concept in Moodle releases. Moodle uses (a) current stable lines and (b) “security support” / “security-only” support windows per line.

### Exact release tarball + SHA256
- Tarball URL (stable501 / 5.1.1):
  - https://download.moodle.org/download.php/stable501/moodle-5.1.1.tgz
- Published SHA256 checksum (same file):
  - https://packaging.moodle.org/stable501/moodle-5.1.1.tgz.sha256
  - `SHA256(moodle-5.1.1.tgz)= 27c94522c3c3e3598e612632500bb5e4385de7c6fe268bd977c6f25705ca5ac1`

### PHP version range for Moodle 5.1
- Minimum: **PHP 8.2.0**.
- Supported: **PHP 8.3.x and 8.4.x**.

### Recommended PHP base image tag
- Use a modern supported PHP for the line. Recommended:
  - `php:8.3-apache`
  - (Optional hardening) pin by digest in `FROM ...@sha256:<digest>` once you’ve selected your base distro variant and verified it in CI.

## 2) MariaDB compatibility

### Moodle 5.1 database minimums
- MariaDB minimum: **10.11.0**.

### Recommended MariaDB Docker image tag to pin
- Prefer an LTS-ish series and pin the image (optionally by digest):
  - `mariadb:11.4`
  - (Optional) pin by digest using the Docker Hub manifest digest for your target platform(s).

## 3) STACK plugin

### Latest stable STACK compatible with the chosen Moodle line
- Current stable STACK listed in the Moodle plugins directory: **STACK 4.11.0** “for Moodle 4.1+” with plugin version **2025102100**.
  - That Moodle compatibility range includes Moodle 5.1.

### ZIP download URL + checksum
- Moodle’s official ZIP download is hosted on moodle.org’s plugins directory, but that directory currently returns **HTTP 403** to the environment used for this research, so I cannot reliably extract the exact `download.php/.../qtype_stack_...zip` URL nor any published checksum from there.
- Practical alternative (works well with your “pinned + checksum” image build approach):
  1. Pin STACK by Git commit from https://github.com/maths/moodle-qtype_stack
  2. Fetch the archive (or clone) at that commit during the Docker build.
  3. Record the computed SHA256 in your repo (treat it as the “published” checksum for *your* build).
- If you still want the Moodle plugins ZIP URL, the reliable way is: open the STACK entry in the Moodle plugins directory in a normal browser and copy the “Download” link; that link is what you would then pin + checksum.

### Required companion plugins
STACK requires additional question behaviours (install docs list them explicitly):
- `qbehaviour_dfexplicitvaildate`
- `qbehaviour_dfcbmexplicitvaildate`
- `qbehaviour_adaptivemultipart`

## 4) goemaxima

### Image tag matching STACK 4.11.0
- The goemaxima project provides an explicit mapping table from STACK plugin version to `STACKMAXIMA_VERSION`. For STACK **4.11.0 (2025102100)**, the mapped `STACKMAXIMA_VERSION` is **2025102100** (Maxima **5.44.0**).
- Recommended Docker tag:
  - `mathinstitut/goemaxima:2025102100-latest`

### Endpoint path
- Documented endpoint path: **`/goemaxima`**.
- Backwards-compatible path: **`/maxima`** (older images accept only `/maxima`; newer should accept both).

## 5) Minimal compatibility tuple (single supported set)

- **Moodle:** 5.1 line, pinned to **5.1.1**
  - https://download.moodle.org/download.php/stable501/moodle-5.1.1.tgz
  - https://packaging.moodle.org/stable501/moodle-5.1.1.tgz.sha256
- **PHP base:** `php:8.3-apache`
- **MariaDB:** `mariadb:11.4`
- **STACK:** 4.11.0 (plugin version 2025102100)
  - Source-of-truth for version/compatibility: Moodle plugins directory “qtype_stack versions” listing.
  - Distribution approach recommended here: pin Git commit from https://github.com/maths/moodle-qtype_stack and record SHA256 in-repo.
  - Companion behaviours:
    - `qbehaviour_dfexplicitvaildate`
    - `qbehaviour_dfcbmexplicitvaildate`
    - `qbehaviour_adaptivemultipart`
- **goemaxima:** `mathinstitut/goemaxima:2025102100-latest`
  - URL path: `/goemaxima` (fallback `/maxima`)
