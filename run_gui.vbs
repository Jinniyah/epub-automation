' epub-automation -- launches the GUI without a visible console window.
'
' Double-click this file (or a shortcut to it -- right-click, "Send to",
' "Desktop (create shortcut)") to start the app. This is explicitly a
' testing-phase stand-in for the real packaged .exe (docs/BACKLOG.md
' Epic 10 Phase B), not a replacement for it: it still requires Python
' and this project's .venv to already be set up on this machine (see
' README.md's "Getting started"), the same one-time setup a technical
' family member does before handing the app to her, same pattern as
' AI-key provisioning and the Windows SmartScreen click-through
' elsewhere in this project's packaging docs.
'
' Uses pythonw.exe (the windowless interpreter that ships with a normal
' CPython install) rather than python.exe, so no console window ever
' appears -- launcher.py itself already opens her default browser to
' the running app (docs/requirements/07-packaging-deployment.md).

Option Explicit

Dim fso, scriptDir, pythonwPath, launcherPath, shell

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = scriptDir & "\.venv\Scripts\pythonw.exe"
launcherPath = scriptDir & "\launcher.py"

If Not fso.FileExists(pythonwPath) Then
    MsgBox "Couldn't find the app's Python environment at:" & vbCrLf & _
        pythonwPath & vbCrLf & vbCrLf & _
        "Make sure the app has been set up first -- see README.md's " & _
        """Getting started"" section (run 'make venv' and 'make install').", _
        vbExclamation, "epub-automation"
    WScript.Quit 1
End If

If Not fso.FileExists(launcherPath) Then
    MsgBox "Couldn't find launcher.py at:" & vbCrLf & launcherPath, _
        vbExclamation, "epub-automation"
    WScript.Quit 1
End If

Set shell = CreateObject("WScript.Shell")
shell.Run """" & pythonwPath & """ """ & launcherPath & """", 0, False
