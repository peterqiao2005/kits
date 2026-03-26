import sqlite3, os

db = os.path.join(os.environ["APPDATA"], "Code", "User", "globalStorage", "state.vscdb")
key = "terminal.history.entries.commands"

con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("SELECT count(*) FROM ItemTable WHERE key=?", (key,))
before = cur.fetchone()[0]

cur.execute("DELETE FROM ItemTable WHERE key=?", (key,))
con.commit()

cur.execute("SELECT count(*) FROM ItemTable WHERE key=?", (key,))
after = cur.fetchone()[0]
con.close()

print("deleted:", before - after, "remaining:", after)
