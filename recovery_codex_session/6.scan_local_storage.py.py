import os, glob

needle = b"call_QZohFxOJ3HUknTul74WrVu0U"

roots = [
    os.path.join(os.environ["APPDATA"], "Code", "Local Storage", "leveldb"),
    os.path.join(os.environ["APPDATA"], "Code", "IndexedDB"),
    os.path.join(os.environ["APPDATA"], "Code", "Local Storage"),
]

files = []
for r in roots:
    if os.path.isdir(r):
        files += glob.glob(os.path.join(r, "**", "*"), recursive=True)

hits = []
for p in files:
    if not os.path.isfile(p):
        continue
    try:
        with open(p, "rb") as f:
            data = f.read()
        if needle in data:
            hits.append(p)
    except Exception:
        pass

print("HIT count:", len(hits))
for p in hits[:200]:
    print(p)
