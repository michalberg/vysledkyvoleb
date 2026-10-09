#!/usr/bin/env python3
"""Vytvoří mock data z voleb 2022 ve stejném formátu jako data/.

Z okrskových dávek 2022 zrekonstruuje průběh sčítání, takže vznikne
realistická historie i rozpracované stavy (bez rozdělených mandátů).

Výstup:
  mock/2022/            konečný stav (všechno sečteno, oficiální mandáty)
  mock/2022-prubeh/     stav uprostřed sčítání – Brno má cca polovinu okrsků,
                        menší MČ jsou částečně už sečtené

Použití:  python3 scripts/mock2022.py
Okrskové dávky (~11 MB) se ukládají do .cache/okrsky2022/.
"""

import copy
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import NS, ROOT, append_history, download, parse, write_index, write_json  # noqa: E402

DATUM = "20220923"
BASE = "https://volby.cz/pls/kv2022"
CACHE = ROOT / ".cache" / "okrsky2022"
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


def stav(final, okrsky, generovano):
    """Sestaví průběžný stav zastupitelstva ze zpracovaných okrsků."""
    if len(okrsky) == final["ucast"]["okrsky_celkem"]:
        data = copy.deepcopy(final)
        data["generovano"] = generovano
        return data
    data = copy.deepcopy(final)
    data["generovano"] = generovano
    data["je_spocteno"] = False
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
    for s in data["strany"]:
        s["hlasy"] = hlasy.get(s["por"], 0)
        s["hlasy_proc"] = round(100 * s["hlasy"] / soucet["PLATNE_HLASY"], 2) if soucet["PLATNE_HLASY"] else 0.0
        s["zastupitele"] = 0
        s["zastupitele_proc"] = 0.0
        s.pop("zvoleni", None)
    return data


def main():
    import json

    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config = {**config, "volby": "kv2022", "datum": DATUM}
    kody = {o["kod"] for o in config["obce"]}

    finals = {}
    for kod in kody:
        finals[kod] = parse(download(f"{BASE}/vysledky_obec?datumvoleb={DATUM}&cislo_obce={kod}"))
        finals[kod]["stazeno"] = None

    for out in (OUT_FINAL, OUT_PRUBEH):
        if out.exists():
            shutil.rmtree(out)

    zpracovane = {kod: {} for kod in kody}  # kod -> cislo okrsku -> (poradi, ucast, hlasy)
    posledni = {}
    prubeh_hotov = False
    for root in load_batches():
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
