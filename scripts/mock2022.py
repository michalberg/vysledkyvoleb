#!/usr/bin/env python3
"""Vytvoří mock data z voleb 2022 ve stejném formátu jako data/.

Z okrskových dávek 2022 zrekonstruuje průběh sčítání, takže vznikne
realistická historie i rozpracované stavy (bez rozdělených mandátů).

Výstup:
  mock/2022/            konečný stav (všechno sečteno, oficiální mandáty)
  mock/2022-prubeh/     stav uprostřed sčítání – Brno má cca polovinu okrsků,
                        menší MČ jsou částečně už sečtené

Konečné výsledky (názvy kandidátek, hlasy, mandáty, zvolení) se berou z registru
KV 2022 na opendata volby.gov.cz, účast a počty okrsků z okrskových dávek.

Použití:  python3 scripts/mock2022.py
Okrskové dávky (~11 MB) a registr se ukládají do .cache/.
"""

import copy
import csv
import io
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import NS, ROOT, append_history, load_config, write_index, write_json  # noqa: E402

DATUM = "20220923"
BASE = "https://volby.cz/pls/kv2022"
CACHE = ROOT / ".cache" / "okrsky2022"
REG_URL = "https://volby.gov.cz/opendata/kv2022/KV2022reg20260328_csv.zip"
REG_CACHE = ROOT / ".cache" / "kv2022reg_csv.zip"
OUT_FINAL = ROOT / "mock" / "2022"
OUT_PRUBEH = ROOT / "mock" / "2022-prubeh"
PRUBEH_KOD = "582786"  # rozpracovaný stav: okamžik, kdy má Brno sečtenou polovinu okrsků
PRUBEH_PODIL = 0.5


def load_batches():
    CACHE.mkdir(parents=True, exist_ok=True)
    batches = []
    i = 1
    while True:
        path = CACHE / f"{i:05d}.xml"
        if not path.exists():
            data = urllib.request.urlopen(f"{BASE}/vysledky_okrsky?datumvoleb={DATUM}&davka={i}", timeout=90).read()
            if b"<DAVKA" not in data or b"<CHYBA" in data:
                break
            path.write_bytes(data)
        batches.append(ET.parse(path).getroot())
        i += 1
    print(f"Dávek: {len(batches)}")
    return batches


def okrsky_z_davky(root, kody):
    """Vrátí (kod, cislo_okrsku, poradi_zprac, ucast, hlasy) pro sledovaná zastupitelstva."""
    for o in root.findall("kv:OKRSEK", NS):
        kod = o.get("KODZASTUP")
        if kod not in kody:
            continue
        u = o.find("kv:UCAST_OKRSEK", NS)
        ucast = {k: int(u.get(k) or 0) for k in ("ZAPSANI_VOLICI", "VYDANE_OBALKY", "ODEVZDANE_OBALKY", "PLATNE_HLASY")}
        hlasy = {int(h.get("POR_STR_HLAS_LIST")): int(h.get("HLASY")) for h in o.findall("kv:HLASY_OKRSEK", NS)}
        yield kod, o.get("CIS_OKRSEK"), int(o.get("PORADI_ZPRAC")), ucast, hlasy


def load_registry(kody, celkem):
    """Konečné výsledky 2022 z registru (kvrzcoco, kvros, kvrk)."""
    if not REG_CACHE.exists():
        REG_CACHE.parent.mkdir(parents=True, exist_ok=True)
        REG_CACHE.write_bytes(urllib.request.urlopen(REG_URL, timeout=120).read())
    zf = zipfile.ZipFile(REG_CACHE)

    def rows(name):
        for r in csv.DictReader(io.StringIO(zf.read(f"csv_od/{name}").decode("utf-8-sig"))):
            if r["DATUMVOLEB"] == DATUM and r["KODZASTUP"] in kody:
                yield r

    def num(v, cast=int):
        return cast(v) if v not in ("", None) else 0

    finals = {}
    for r in rows("kvrzcoco.csv"):
        kod = r["KODZASTUP"]
        finals[kod] = {
            "kod": kod, "nazev": r["NAZEVZAST"], "typ": "OBEC" if r["TYPZASTUP"] == "1" else "MCMO",
            "voleno": int(r["MANDATY"]), "pocet_obvodu": 1, "je_spocteno": True, "generovano": None,
            "ucast": {"okrsky_celkem": celkem.get(kod, 0), "okrsky_zprac": 0, "okrsky_zprac_proc": 0.0,
                      "zapsani_volici": 0, "vydane_obalky": 0, "ucast_proc": 0.0, "volicske_prukazy": None,
                      "odevzdane_obalky": 0, "platne_listky": None, "platne_hlasy": 0},
            "strany": [],
        }
    kandidatu, zvoleni = {}, {}
    for r in rows("kvrk.csv"):
        key = (r["KODZASTUP"], int(r["POR_STR_HL"]))
        if r["PLATNOST"] == "A":
            kandidatu[key] = kandidatu.get(key, 0) + 1
        if r["MANDAT"] == "A":
            zvoleni.setdefault(key, []).append({
                "poradi": int(r["PORCISLO"]), "hlasy": num(r["POCHLASU"]), "hlasy_proc": num(r["POCPROCVSE"], float),
                "titul_pred": r["TITULPRED"], "jmeno": r["JMENO"], "prijmeni": r["PRIJMENI"], "titul_za": r["TITULZA"]})
    for r in rows("kvros.csv"):
        kod, por = r["KODZASTUP"], int(r["POR_STR_HL"])
        strana = {"por": por, "vstrana": int(r["VSTRANA"]), "hlasy": num(r["HLASY_STR"]), "hlasy_proc": num(r["PROCHLSTR"], float),
                  "kandidatu": kandidatu.get((kod, por), 0), "zastupitele": num(r["MAND_STR"]), "zastupitele_proc": 0.0,
                  "nazev": r["NAZEVCELK"]}
        voleno = finals[kod]["voleno"]
        strana["zastupitele_proc"] = round(100 * strana["zastupitele"] / voleno, 2) if voleno else 0.0
        if (kod, por) in zvoleni:
            strana["zvoleni"] = sorted(zvoleni[(kod, por)], key=lambda z: z["poradi"])
        finals[kod]["strany"].append(strana)
    for f in finals.values():
        f["strany"].sort(key=lambda s: s["por"])
    return finals


def stav(final, okrsky, generovano):
    """Sestaví průběžný stav zastupitelstva ze zpracovaných okrsků."""
    hotovo = len(okrsky) == final["ucast"]["okrsky_celkem"]
    data = copy.deepcopy(final)
    data["generovano"] = generovano
    data["je_spocteno"] = hotovo
    soucet = {k: 0 for k in ("ZAPSANI_VOLICI", "VYDANE_OBALKY", "ODEVZDANE_OBALKY", "PLATNE_HLASY")}
    hlasy = {}
    for _, ucast, h in okrsky.values():
        for k in soucet:
            soucet[k] += ucast[k]
        for por, n in h.items():
            hlasy[por] = hlasy.get(por, 0) + n
    u = data["ucast"]
    celkem = u["okrsky_celkem"]
    u.update(
        okrsky_zprac=len(okrsky),
        okrsky_zprac_proc=round(100 * len(okrsky) / celkem, 2),
        zapsani_volici=soucet["ZAPSANI_VOLICI"],
        vydane_obalky=soucet["VYDANE_OBALKY"],
        odevzdane_obalky=soucet["ODEVZDANE_OBALKY"],
        platne_hlasy=soucet["PLATNE_HLASY"],
        ucast_proc=round(100 * soucet["VYDANE_OBALKY"] / soucet["ZAPSANI_VOLICI"], 2) if soucet["ZAPSANI_VOLICI"] else 0.0,
    )
    if hotovo:
        # konečný stav: oficiální hlasy z registru (mohou zahrnovat pozdější opravy výsledků)
        u["platne_hlasy"] = sum(s["hlasy"] for s in data["strany"])
        return data
    for s in data["strany"]:
        s["hlasy"] = hlasy.get(s["por"], 0)
        s["hlasy_proc"] = round(100 * s["hlasy"] / soucet["PLATNE_HLASY"], 2) if soucet["PLATNE_HLASY"] else 0.0
        s["zastupitele"] = 0
        s["zastupitele_proc"] = 0.0
        s.pop("zvoleni", None)
    return data


def main():
    import json

    config = load_config()
    config = {**config, "volby": "kv2022", "datum": DATUM}
    kody = {o["kod"] for o in config["obce"]}

    batches = load_batches()
    posledni_okrsky = {kod: {} for kod in kody}
    for root in batches:
        for kod, okrsek, poradi, _, _ in okrsky_z_davky(root, kody):
            posledni_okrsky[kod][okrsek] = poradi
    finals = load_registry(kody, {k: len(v) for k, v in posledni_okrsky.items()})
    chybi = kody - finals.keys()
    if chybi:
        sys.exit(f"V registru 2022 chybí: {sorted(chybi)}")

    for out in (OUT_FINAL, OUT_PRUBEH):
        if out.exists():
            shutil.rmtree(out)

    zpracovane = {kod: {} for kod in kody}  # kod -> cislo okrsku -> (poradi, ucast, hlasy)
    posledni = {}
    prubeh_hotov = False
    for root in batches:
        generovano = root.get("DATUM_CAS_GENEROVANI")
        zmenene = set()
        for kod, okrsek, poradi, ucast, hlasy in okrsky_z_davky(root, kody):
            stary = zpracovane[kod].get(okrsek)
            if stary is None or poradi > stary[0]:
                zpracovane[kod][okrsek] = (poradi, ucast, hlasy)
                zmenene.add(kod)
        for kod in sorted(zmenene):
            data = stav(finals[kod], zpracovane[kod], generovano)
            data["stazeno"] = generovano
            posledni[kod] = data
            for out in (OUT_FINAL,) if prubeh_hotov else (OUT_FINAL, OUT_PRUBEH):
                append_history(out, data, generovano)

        brno = posledni.get(PRUBEH_KOD)
        if not prubeh_hotov and brno and brno["ucast"]["okrsky_zprac"] >= PRUBEH_PODIL * brno["ucast"]["okrsky_celkem"]:
            for kod in kody:
                data = posledni.get(kod) or stav(finals[kod], {}, generovano)
                write_json(OUT_PRUBEH / "latest" / f"{kod}.json", data)
            write_index(OUT_PRUBEH, config, generovano)
            prubeh_hotov = True
            print(f"Průběžný stav: {generovano}")

    for kod in kody:
        data = posledni[kod]
        if not data["je_spocteno"]:
            print(f"VAROVÁNÍ {kod}: z dávek nevyšel kompletní stav", file=sys.stderr)
        write_json(OUT_FINAL / "latest" / f"{kod}.json", data)
    write_index(OUT_FINAL, config, max(d["generovano"] for d in posledni.values()))

    for out in (OUT_FINAL, OUT_PRUBEH):
        idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
        print(f"\n{out.relative_to(ROOT)}:")
        for o in idx["obce"]:
            print(f"  {o['nazev']:32} {o['okrsky_zprac']:>3}/{o['okrsky_celkem']:<3} spočteno={o['je_spocteno']}")


if __name__ == "__main__":
    main()
