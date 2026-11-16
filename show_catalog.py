import json

d = json.load(open("catalog/catalog.json", encoding="utf-8"))
g = d["games"]["Blox Fruits"]
for bucket in ("noKey", "key"):
    print("===", bucket)
    for s in g[bucket]:
        print(f"  {s['title'][:45]:45} | views {s['views']:>7} | place {s['placeId']}")
print()
tot_n = sum(len(x.get("noKey", [])) for x in d["games"].values())
tot_k = sum(len(x.get("key", [])) for x in d["games"].values())
print("games:", len(d["games"]), "| noKey:", tot_n, "| key:", tot_k)
