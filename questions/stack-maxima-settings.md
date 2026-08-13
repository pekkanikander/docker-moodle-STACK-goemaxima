# STACK Maxima Settings for goemaxima (Internet Needed)

Context: We are building an OSS Docker Compose setup for Moodle 5.1.1 + STACK 4.11.0
(plugin version 2025102100) with goemaxima `mathinstitut/goemaxima:2025102100-1.2.0`.
STACK is installed in `question/type/stack`, and Moodle runs with `$CFG->dirroot`
at `/var/www/html/public`.

We need the correct values for these STACK settings so we can automate them via
`admin/cli/cfg.php`:

- `qtype_stack/maximaversion`
- `qtype_stack/maximacommand`
- `qtype_stack/maximacommandopt`
- `qtype_stack/maximacommandserver` (URL for the goemaxima pool)
- `qtype_stack/maximalibraries`

## Questions to answer
1) For STACK 4.11.0 + goemaxima 2025102100-1.2.0, what are the recommended values
   for each of the settings above? Please provide sources.
2) Should `maximacommand` and `maximacommandopt` be set when using goemaxima,
   or are they only for local maxima installs? (Cite docs.)
3) For `maximalibraries`, what is the default/empty value if we want to load none?
4) Confirm the correct goemaxima URL to use inside Docker Compose (service name `maxima`).

## Output format requested
Please output a block we can paste into `.env`:

```
MOODLE_STACK_MAXIMAVERSION=...
MOODLE_STACK_MAXIMACOMMAND=...
MOODLE_STACK_MAXIMACOMMANDOPT=...
MOODLE_STACK_MAXIMACOMMANDSERVER=...
MOODLE_STACK_MAXIMALIBRARIES=...
```



## Answers (STACK 4.11.0 / plugin 2025102100 + goemaxima 2025102100-1.2.0)

### 1) Recommended values

**`qtype_stack/maximaversion`**

Set this to the Maxima version bundled by the goemaxima image that matches your STACK plugin version.

For STACK **4.11.0** (Moodle plugin version **2025102100**), the goemaxima compatibility table lists **Maxima 5.44.0** as the included Maxima version.

Source: goemaxima README “What Stackmaxima version do I need?” (row for Moodle Stack Version `2025102100`).

**`qtype_stack/maximacommandserver`**

When using goemaxima, STACK should be pointed at the goemaxima HTTP endpoint. The goemaxima README states the service listens on port **8080** in the container and that the path to input into STACK is `http://[address:port]/goemaxima` (with `/maxima` only for some older images).

Inside Docker Compose, using the service name `maxima`, the URL is:

- `http://maxima:8080/goemaxima`

Source: goemaxima README “Using the Docker Image”.

**`qtype_stack/maximacommand`** and **`qtype_stack/maximacommandopt`**

These are for **direct/local** Maxima execution (i.e., when Moodle runs Maxima locally via a command line). When using goemaxima (remote/server mode), you should leave these **empty**.

Rationale/sources:
- STACK installation docs explicitly recommend using goemaxima (via docker) and connecting to Maxima “that way” in scenarios where direct/local Maxima is not used (e.g. Windows). This is the server/remote model.
- Older STACK guidance for “Platform type: Server” used `qtype_stack/maximacommand` to hold the *URL* of the server; the existence of the dedicated `maximacommandserver` setting in newer versions reflects the same split: local command vs server URL.

Sources:
- STACK installation docs (“set up a server with goemaxima … and connect your server to Maxima that way”).
- Moodle forum thread noting that for “Platform type: Server” the Maxima command setting is a URL (i.e., not a local command), illustrating the conceptual split.

**`qtype_stack/maximalibraries`**

This is a comma-separated list of optional Maxima libraries to load. The STACK docs state the current default is:

- `stats, distrib, descriptive`

Source: STACK docs “Testing installation → Maxima optional packages”.

If you want to load **none**, set this to the **empty string** (i.e., no entries in the comma-separated list).

### 2) Should `maximacommand` and `maximacommandopt` be set with goemaxima?

No. With goemaxima you configure the **server URL** (`maximacommandserver`). The local command settings are for running Maxima on the Moodle host.

Sources:
- goemaxima README instructs setting the HTTP endpoint in STACK (i.e., a URL, not a local executable path).
- STACK installation docs recommend goemaxima as the server-based approach.

### 3) `maximalibraries` empty/default value

- Default (per STACK docs): `stats, distrib, descriptive`.
- “Load none”: empty string.

### 4) Correct goemaxima URL inside Docker Compose (service name `maxima`)

Use:

- `http://maxima:8080/goemaxima`

Source: goemaxima README (port 8080; `/goemaxima` path).

## Output block for `.env`

```dotenv
MOODLE_STACK_MAXIMAVERSION=5.44.0
MOODLE_STACK_MAXIMACOMMAND=
MOODLE_STACK_MAXIMACOMMANDOPT=
MOODLE_STACK_MAXIMACOMMANDSERVER=http://maxima:8080/goemaxima
MOODLE_STACK_MAXIMALIBRARIES=stats, distrib, descriptive
```

## Source links

- goemaxima README (endpoint path/port + version mapping table): https://github.com/mathinstitut/goemaxima
- STACK installation docs (goemaxima via docker + connect server to Maxima): https://docs.stack-assessment.org/en/Installation/
- STACK testing/install docs (default optional packages / `maximalibraries`): https://docs.stack-assessment.org/en/Installation/Testing_installation/
- Moodle forum example of “Server” platform using a URL in the “Maxima command” setting (historical but illustrates local-vs-server split): https://moodle.org/mod/forum/discuss.php?d=386113
