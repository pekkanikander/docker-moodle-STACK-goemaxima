# STACK Behaviour Plugin Versions (Internet Needed)

Context: We are building an OSS Docker Compose setup for Moodle + MariaDB + STACK + goemaxima.
STACK 4.11.0 (plugin version 2025102100) is pinned for Moodle 5.1.1. We need to pin the
required companion *question behaviour* plugins with exact versions and checksums.

Please answer with sources/links and concrete version choices.

## Required plugins (names as currently understood)
- `qbehaviour_dfexplicitvaildate` (deferred feedback + explicit validation)
- `qbehaviour_dfcbmexplicitvaildate` (same, with CBM)
- `qbehaviour_adaptivemultipart` (adaptive multipart)

## Questions to answer
1) Are these the exact plugin names/paths required by STACK 4.11.0?
2) What are the latest stable versions compatible with Moodle 5.1.x and STACK 4.11.0?
3) Provide the exact download URLs for each plugin:
   - Prefer the Moodle plugins directory ZIP if available.
   - Otherwise, provide the GitHub release asset (or tag archive) URL.
4) Provide checksums for each plugin archive:
   - If the download is a GitHub *release asset*, use the Releases REST API `digest` field.
   - If only a tag archive exists, compute SHA256 and report it.
5) Provide any compatibility notes (minimum Moodle version, known issues).

## Final output format requested
For each plugin:
- plugin_name:
  - version:
  - source_url:
  - sha256:
  - notes:

Include citations/links for each version and download URL.

---

## Answers (researched)

### 1) Exact plugin names/paths required by STACK 4.11.0

Yes — the question behaviour plugins you listed match the names used by STACK’s own installation instructions, and their Moodle install paths are:

- `qbehaviour_dfexplicitvaildate` → `question/behaviour/dfexplicitvaildate` citeturn2search9turn3search4
- `qbehaviour_dfcbmexplicitvaildate` → `question/behaviour/dfcbmexplicitvaildate` citeturn2search9turn3search4
- `qbehaviour_adaptivemultipart` → `question/behaviour/adaptivemultipart` citeturn2search9turn3search4

(These are the directory names STACK docs tell you to rename to after unzipping.) citeturn2search9turn3search4

### 2) Latest stable versions compatible with Moodle 5.1.x and STACK 4.11.0

**Observed state (from Moodle Plugins Directory):**

- STACK **4.11.0** is listed as “for Moodle 4.1+” (plugin version/build **2025102100**). citeturn0search7
- The three behaviour plugins’ latest stable releases are all from **2022-09-22**, and are listed as supported up to **Moodle 4.5** (not Moodle 5.1).
  - `dfexplicitvaildate` **4.2.2** (build **2022092200**) supports Moodle 3.9–4.5. citeturn3search0turn7search5
  - `dfcbmexplicitvaildate` **4.2.2** (build **2022092200**) (same 2022-09-22 set; Moodle directory lists it as current). citeturn6search4turn7search1turn7search0
  - `adaptivemultipart` **4.3.8** (build **2022092200**) supports Moodle 3.9–4.5. citeturn5search0turn5search1

**Implication for Moodle 5.1.x:** there is **no explicit confirmation** (in the plugin directory metadata) that these behaviour plugins are supported on Moodle 5.1.x yet. They may still work in practice, but that would be “works unless something broke” rather than “declared compatible”. citeturn3search0turn5search0turn7search0

### 3) Exact download URLs

Because automated fetching of the Moodle plugins ZIPs is blocked from this environment (HTTP 403), I’m giving both:

- **Preferred**: Moodle plugins directory ZIP (exact plugin + version)
- **Alternative**: GitHub tag archive (deterministic, based on the VCS tag shown on the plugin version page)

#### qbehaviour_dfexplicitvaildate
- Moodle ZIP (4.2.2 / 2022092200):
  - `https://moodle.org/plugins/download.php/27603/qbehaviour_dfexplicitvaildate_moodle45_2022092200.zip` citeturn2search15turn3search0
- GitHub tag archive (v4.2.2):
  - `https://github.com/maths/moodle-qbehaviour_dfexplicitvaildate/archive/refs/tags/v4.2.2.zip` citeturn3search0turn3search1

#### qbehaviour_dfcbmexplicitvaildate
- Moodle ZIP (4.2.2 / 2022092200):
  - `https://moodle.org/plugins/download.php/27604/qbehaviour_dfcbmexplicitvaildate_moodle45_2022092200.zip` citeturn6search4turn7search0
- GitHub tag archive (v4.2.2):
  - `https://github.com/maths/moodle-qbehaviour_dfcbmexplicitvaildate/archive/refs/tags/v4.2.2.zip` citeturn7search0turn3search2

#### qbehaviour_adaptivemultipart
- Moodle ZIP (4.3.8 / 2022092200):
  - `https://moodle.org/plugins/download.php/27605/qbehaviour_adaptivemultipart_moodle45_2022092200.zip` citeturn5search0turn5search1
- GitHub tag archive (v4.3.8):
  - `https://github.com/maths/moodle-qbehaviour_adaptivemultipart/archive/refs/tags/v4.3.8.zip` citeturn5search0turn10search6

### 4) Checksums (sha256)

**Not computable in this environment** (downloads are blocked), but Moodle publishes an **MD5** for each archive, and you can compute SHA256 in CI during image build.

Published MD5 values:
- `qbehaviour_dfexplicitvaildate` 4.2.2: `803b4a46a11c6792a878e133b775da6c` citeturn3search0turn6search1
- `qbehaviour_dfcbmexplicitvaildate` 4.2.2: `ec0f8999df04bdca7e7c6583f107ecb3` citeturn7search0
- `qbehaviour_adaptivemultipart` 4.3.8: `40f108dc4e41f691af5fc804c2c9868d` citeturn5search0

Suggested reproducible SHA256 step (run in CI, for each URL):

```sh
curl -fsSL "$URL" -o plugin.zip
sha256sum plugin.zip
```

### 5) Compatibility notes / known issues

- All three behaviour plugins are described as “part of set STACK” in the Moodle Plugins directory metadata. citeturn3search0turn5search0turn7search0
- Latest published stable releases of the behaviour plugins are from 2022-09-22 and list support through Moodle 4.5; Moodle 5.1.x is not listed there (so treat as *not declared* compatible). citeturn3search0turn5search0turn7search0
- STACK itself is listed as supporting “Moodle 4.1+” for STACK 4.11.0. citeturn0search7

### Final pinning block (copy/paste)

```yaml
qbehaviour_dfexplicitvaildate:
  version: "4.2.2"           # build 2022092200
  source_url: "https://moodle.org/plugins/download.php/27603/qbehaviour_dfexplicitvaildate_moodle45_2022092200.zip"
  sha256: "TODO-compute-in-CI"  # Moodle publishes MD5: 803b4a46a11c6792a878e133b775da6c
  notes: "Latest stable listed in plugins directory; declared support Moodle 3.9–4.5; VCS tag v4.2.2."

qbehaviour_dfcbmexplicitvaildate:
  version: "4.2.2"           # build 2022092200
  source_url: "https://moodle.org/plugins/download.php/27604/qbehaviour_dfcbmexplicitvaildate_moodle45_2022092200.zip"
  sha256: "TODO-compute-in-CI"  # Moodle publishes MD5: ec0f8999df04bdca7e7c6583f107ecb3
  notes: "Latest stable listed in plugins directory; declared support Moodle 3.9–4.5 (5.1 not listed); same 2022-09-22 STACK set."

qbehaviour_adaptivemultipart:
  version: "4.3.8"           # build 2022092200
  source_url: "https://moodle.org/plugins/download.php/27605/qbehaviour_adaptivemultipart_moodle45_2022092200.zip"
  sha256: "TODO-compute-in-CI"  # Moodle publishes MD5: 40f108dc4e41f691af5fc804c2c9868d
  notes: "Latest stable listed in plugins directory; declared support Moodle 3.9–4.5; VCS tag v4.3.8."
```
