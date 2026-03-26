import os, glob, sqlite3

needle = "novel_tts_pipeline"
root = os.path.join(os.environ["APPDATA"], "Code", "User")

dbs = glob.glob(os.path.join(root, "**", "*.vscdb"), recursive=True)

print("DB count:", len(dbs))
hit = 0

for db in dbs:
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        if "ItemTable" in tables:
            cur.execute("SELECT key FROM ItemTable WHERE value LIKE ?", (f"%{needle}%",))
            rows = cur.fetchall()
            if rows:
                hit += 1
                print("\nHIT DB:", db)
                for (k,) in rows[:30]:
                    print("  KEY:", k)
        con.close()
    except Exception:
        pass

print("\nHIT DB total:", hit)
