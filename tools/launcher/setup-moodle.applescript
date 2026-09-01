-- Source of "Setup Moodle.app" (repo root). After editing, rebuild with:
--   osacompile -o "Setup Moodle.app" tools/launcher/setup-moodle.applescript
-- The built app is committed: CI runners are Linux and cannot run osacompile.
-- The app is unsigned; it runs because git clones carry no quarantine xattr.
-- A repo downloaded as a GitHub ZIP is quarantined and Gatekeeper blocks it.
--
-- Runs tools/start.sh in the background and follows its "== " phase lines in
-- the applet's native progress window. The engine's exit status arrives via
-- .generated/setup.exit.

on run
	set appPath to POSIX path of (path to me)
	set repoRoot to do shell script "dirname " & quoted form of appPath
	set logFile to repoRoot & "/.generated/setup.log"
	set exitFile to repoRoot & "/.generated/setup.exit"

	set enginePid to do shell script "cd " & quoted form of repoRoot & " && mkdir -p .generated && rm -f " & quoted form of exitFile & "; ( ./tools/start.sh > " & quoted form of logFile & " 2>&1; echo $? > " & quoted form of exitFile & " ) > /dev/null 2>&1 & echo $!"

	set progress total steps to 8
	set progress completed steps to 0
	set progress description to "Setting up Moodle"
	set progress additional description to "Starting. The first run can take several minutes."

	set exitText to ""
	try
		repeat 3600 times -- polled every 2 s: gives up after 2 h
			set exitText to do shell script "cat " & quoted form of exitFile & " 2>/dev/null; true"
			if exitText is not "" then exit repeat
			set phaseText to do shell script "awk '/^== /{p=substr($0,4)} END{print p}' " & quoted form of logFile & " 2>/dev/null; true"
			set phaseCount to do shell script "awk '/^== /{n++} END{print n+0}' " & quoted form of logFile & " 2>/dev/null || echo 0"
			if phaseText is not "" then set progress additional description to phaseText
			set progress completed steps to (phaseCount as integer)
			delay 2
		end repeat
	on error number -128 -- the progress window's Stop button
		do shell script "pkill -TERM -P " & enginePid & " 2>/dev/null; kill -TERM " & enginePid & " 2>/dev/null; true"
		display dialog "Setup stopped. Nothing is broken: double-click Setup Moodle to start over." buttons {"OK"} default button "OK"
		return
	end try

	if exitText is "0" then
		set progress completed steps to 8
		display dialog "Moodle is ready." & return & return & "Log in with:" & return & "    username:  admin" & return & "    password:  (leave empty)" & return & return & "This local instance is passwordless; it only listens on this machine." buttons {"OK"} default button "OK"
	else
		-- a nonzero exit, or the 2 h timeout (exit file never appeared)
		do shell script "pkill -TERM -P " & enginePid & " 2>/dev/null; kill -TERM " & enginePid & " 2>/dev/null; true"
		try
			do shell script "open -e " & quoted form of logFile
		end try
		display dialog "Moodle setup failed." & return & return & "The setup log has been opened; the last lines usually explain the problem." buttons {"OK"} default button "OK" with icon stop
	end if
end run
