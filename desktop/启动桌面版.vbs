Set o = CreateObject("Wscript.Shell")
desktop = "C:\Users\1\Documents\Default Project\desktop"
exe = desktop & "\node_modules\electron\dist\electron.exe"
cmd = """" & exe & """ """ & desktop & """"
o.Run cmd, 1, False