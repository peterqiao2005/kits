import sqlite3, os, sys

db = os.path.join(os.environ["APPDATA"], "Code", "User", "globalStorage", "state.vscdb")
key = "terminal.history.entries.commands"

con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
row = cur.fetchone()
con.close()

out = os.path.join(os.path.expanduser("~"), "vscode_terminal_history_commands_backup.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write(row[0] if row else "")
print("exported:", out, "found:", bool(row))
