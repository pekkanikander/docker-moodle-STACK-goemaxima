# STACK Behaviour Dependencies Rationale (Internet Needed)

Context: Moodle 5.1 + STACK 4.11.0. STACK’s `version.php` lists required question behaviour
plugins (`qbehaviour_adaptivemultipart`, `qbehaviour_dfexplicitvaildate`,
`qbehaviour_dfcbmexplicitvaildate`). We need to understand why they are required and
whether they can be optional or safely installed on Moodle 5.1.

Please answer with sources/links and concise conclusions.

## Questions to answer
1) Why does STACK require these behaviour plugins? Are they hard dependencies or just for certain features?
2) Is it safe to install these plugins on Moodle 5.1 even though the plugin directory only lists support up to 4.5?
3) Can STACK be used without them (e.g., by editing dependency list), or will Moodle block installation?
4) Are there newer forks/versions of these behaviours that support Moodle 5.1?

## Final output format requested
- Summary recommendation
- Evidence/links
- Any compatibility notes or suggested workarounds

---

## Answers (research notes)

### Summary recommendation
- Treat `qbehaviour_adaptivemultipart`, `qbehaviour_dfexplicitvaildate`, and `qbehaviour_dfcbmexplicitvaildate` as **hard dependencies** for STACK as shipped; do not try to “make them optional” by editing `version.php` unless you are willing to maintain a fork and accept breakage risk.
- For Moodle **5.1**, install the **latest upstream** of each behaviour (either from the Moodle plugins directory or directly from the official GitHub repos). Although the plugins directory UI currently lists compatibility only up to 4.5 for some of these, the codebases are still maintained and STACK itself is tested up to Moodle 5.1.
- If Moodle 5.1 refuses installation due to stated compatibility in the plugins directory UI, install from Git and rely on the plugin’s own `version.php` constraints (what Moodle actually enforces).

### 1) Why does STACK require these behaviour plugins?
STACK’s own installation instructions explicitly state it “requires” these additional question behaviours, and points to these specific three behaviours. These behaviours exist to support the “STACK way” of doing formative checking and multi-part attempt flows:

- `qbehaviour_adaptivemultipart`: an adaptive-mode behaviour designed for **multi-part** questions, letting different parts register tries independently as inputs become valid/changed. This behaviour was created “for use with STACK”.
- `qbehaviour_dfexplicitvaildate`: a **deferred feedback** behaviour with an explicit **Check** button that lets students validate syntax/inputs during an attempt (without submitting the whole attempt for grading).
- `qbehaviour_dfcbmexplicitvaildate`: as above, but for **deferred feedback with CBM** (certainty-based marking) plus explicit validation.

These map to concrete quiz UX features (multi-part tries; “Check” during deferred modes). In principle, if you never select these behaviours in quizzes, STACK questions could still render and grade under other behaviours — but STACK declares them as dependencies, so Moodle will treat them as required at install time.

Evidence:
- STACK installation docs: “Add some additional question behaviours. STACK requires these.” and lists these three behaviours with Git clone instructions. citeturn2search24
- GitHub README text for each behaviour describes its purpose and explicitly states it was created for use with STACK. citeturn2search0turn2search1turn2search2

### 2) Is it safe to install these plugins on Moodle 5.1 even though the plugin directory only lists support up to 4.5?
What matters operationally is what Moodle enforces from the plugin’s own `version.php` (minimum Moodle version, dependencies), not the plugins directory “supported up to …” metadata. Moodle’s `version.php` mechanism is explicitly where dependencies and minimum version are declared. citeturn2search15

Empirically, the Moodle plugins directory lists current releases for the explicit-validation behaviours that are marked compatible through **Moodle 4.5**, not 5.1. citeturn0search2turn0search3

However:
- The official STACK repo documentation states STACK has been tested on Moodle **4.1 to 5.1 inclusive**. citeturn0search5
- The behaviour repos are still being maintained (recent updates on GitHub), which is a stronger signal than the plugins directory compatibility label being up-to-date. citeturn2search16turn7search22

Conclusion: **likely safe in practice**, but not formally “certified” by the plugins directory metadata for 5.1 at the time of writing. If you want higher confidence, run Moodle’s built-in plugin upgrade checks in a staging environment and run STACK’s healthcheck afterwards.

### 3) Can STACK be used without them (e.g., by editing dependency list), or will Moodle block installation?
Moodle will block installation when declared dependencies are missing, because dependencies are declared in the plugin’s `version.php` and enforced by Moodle’s plugin manager. citeturn2search15

Workarounds:
- **Manual fork**: remove/alter the dependency list in STACK’s `version.php` and maintain your own fork. This may get you past the installer, but it increases maintenance burden (you now own a divergence from upstream) and you can still hit runtime issues if STACK code paths assume those behaviours exist.
- **Install the behaviours**: simplest and upstream-aligned.

Practical recommendation: do not fork unless you have a strong, test-backed reason.

### 4) Are there newer forks/versions of these behaviours that support Moodle 5.1?
As of the sources checked here:
- The canonical upstream for these behaviours appears to be the `maths/*` GitHub repositories, and these are what STACK’s own installation docs point to. citeturn2search24turn2search0turn2search1turn2search2
- The Moodle plugins directory shows the latest published versions for the explicit-validation behaviours and lists compatibility through Moodle 4.5. citeturn0search2turn0search3

I did not find a clearly-established “new fork” whose primary purpose is “Moodle 5.1 compatibility”. The most credible path is therefore:
- install the latest official versions (plugins directory or GitHub),
- validate in staging on Moodle 5.1,
- and if you encounter a specific incompatibility, pin known-good commits/tags and/or contribute a fix upstream.

### Compatibility notes / suggested workarounds
- Treat the Moodle plugins directory compatibility labels as “tested up to” rather than “won’t work beyond”. For Moodle 5.1, prefer upstream GitHub for latest compatibility fixes.
- If you are building Docker images: pin each behaviour repo by tag/commit (same strategy you’ll use for STACK and goemaxima) and run an automated smoke test (Moodle CLI upgrade + STACK healthcheck).
