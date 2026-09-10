Option Explicit
Dim shell, fso, root, pythonw, launcher, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(root, "runtime\pythonw.exe")
launcher = fso.BuildPath(root, "app\scripts\windows_launcher.py")
command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & launcher & Chr(34)
shell.Run command, 0, False
