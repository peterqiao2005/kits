import os, glob, sqlite3

needle = "call_QZohFxOJ3HUknTul74WrVu0U"
root = os.path.join(os.environ["APPDATA"], "Code", "User")

dbs = glob.glob(os.path.join(root, "**", "*.vscdb"), recursive=True)

print("DB count:", len(dbs))
hits = 0

for db in dbs:
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        if "ItemTable" not in tables:
            con.close()
            continue

        cur.execute("SELECT key FROM ItemTable WHERE value LIKE ?", (f"%{needle}%",))
        rows = cur.fetchall()
        con.close()

        if rows:
            hits += 1
            print("\nHIT DB:", db)
            for (k,) in rows[:200]:
                print("  KEY:", k)
    except Exception:
        pass

print("\nHIT DB total:", hits)
