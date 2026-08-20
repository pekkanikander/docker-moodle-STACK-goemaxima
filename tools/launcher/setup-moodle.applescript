-- Source of "Setup Moodle.app" (repo root). After editing, rebuild with:
--   osacompile -o "Setup Moodle.app" tools/launcher/setup-moodle.applescript
-- The built app is committed: CI runners are Linux and cannot run osacompile.
-- The app is unsigned; it runs because git clones carry no quarantine xattr.
-- A repo downloaded as a GitHub ZIP is quarantined and Gatekeeper blocks it.

on run
	set appPath to POSIX path of (path to me)
	set repoRoot to do shell script "dirname " & quoted form of appPath
	set logFile to repoRoot & "/.generated/setup.log"
	try
		with timeout of 7200 seconds
			do shell script "cd " & quoted form of repoRoot & " && mkdir -p .generated && SETUP_NOTIFY=1 ./tools/start.sh > " & quoted form of logFile & " 2>&1"
		end timeout
	on error
		try
			do shell script "open -e " & quoted form of logFile
		end try
		display dialog "Moodle setup failed." & return & return & "The setup log has been opened; the last lines usually explain the problem." buttons {"OK"} default button "OK" with icon stop
		return
	end try
	display dialog "Moodle is ready." & return & return & "Log in with:" & return & "    username:  admin" & return & "    password:  Change-me!" & return & return & "You will be asked to choose a new password at first login." buttons {"OK"} default button "OK"
end run
