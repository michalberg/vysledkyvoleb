#!/usr/bin/env python3
"""Vytvoří strany.json – číselník volebních stran (VSTRANA) pro sledovaná zastupitelstva.

Zdroj: číselníky KV 2026 na volby.gov.cz (cvs = volební strany,
cvs_slozeni + cns = složení koalic a sdružení).

Do strany.json se dostanou jen kódy, které se vyskytují v data/latest/.
"""

import csv
import io
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://volby.gov.cz/opendata/kv2026/KV2026ciselniky20261007_csv.zip"
TYPY = {"S": "strana/hnutí", "K": "koalice", "D": "sdružení s nezávislými", "M": "nezávislí kandidáti"}


def main():
    zf = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(URL, timeout=60).read()))

    def read(name):
        return list(csv.DictReader(io.StringIO(zf.read(f"csv_od/{name}").decode("utf-8-sig"))))

    cvs = {r["VSTRANA"]: r for r in read("cvs.csv")}
    cns = {r["NSTRANA"]: r for r in read("cns.csv")}
    slozeni = {}
    for r in read("cvs_slozeni.csv"):
        slozeni.setdefault(r["VSTRANA"], []).append(r["NSTRANA"])

    used = set()
    for path in (ROOT / "data" / "latest").glob("*.json"):
        for s in json.loads(path.read_text(encoding="utf-8"))["strany"]:
            used.add(str(s["vstrana"]))

    strany = {}
    for v in sorted(used, key=int):
        r = cvs[v]
        strany[v] = {
            "nazev": r["NAZEV_STRV"],
            "zkratka": r["ZKRATKAV30"],
            "zkratka8": r["ZKRATKAV8"],
            "typ": TYPY.get(r["TYPVS"], r["TYPVS"]),
            "slozeni": [cns[n]["ZKRATKAN30"] for n in slozeni.get(v, []) if n in cns],
        }
    (ROOT / "strany.json").write_text(json.dumps(strany, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"strany.json: {len(strany)} kódů")


if __name__ == "__main__":
    main()
