#!/usr/bin/env python3
"""Stáhne průběžné výsledky voleb do zastupitelstev obcí z volby.gov.cz
a uloží je jako JSON.

Výstup (vše v adresáři data/):
  latest/<kod>.json    aktuální stav zastupitelstva
  history/<kod>.jsonl  jeden řádek na každou změnu výsledků (pro grafy vývoje)
  raw/<kod>.xml        poslední stažené XML (pro kontrolu)
  index.json           přehled sledovaných zastupitelstev

Soubory se přepisují jen při skutečné změně výsledků. Pokud se stažení
nepovede (nedostupný server, chybné XML), zůstanou poslední uložená data.
"""

import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NS = {"kv": "http://www.volby.cz/kv/"}
TZ = ZoneInfo("Europe/Prague")
URL = "https://volby.gov.cz/appdata/{volby}/{datum}/odata/zastup/vysledky_obec_{kod}.xml"
TIMEOUT = 20
RETRIES = 3


def num(value):
    """Převede číselný atribut na int/float, ostatní nechá jako text."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def attrs(el, mapping):
    return {key: num(el.get(attr)) for key, attr in mapping.items()}


UCAST = {
    "okrsky_celkem": "OKRSKY_CELKEM",
    "okrsky_zprac": "OKRSKY_ZPRAC",
    "okrsky_zprac_proc": "OKRSKY_ZPRAC_PROC",
    "zapsani_volici": "ZAPSANI_VOLICI",
    "vydane_obalky": "VYDANE_OBALKY",
    "ucast_proc": "UCAST_PROC",
    "volicske_prukazy": "VOLICSKE_PRUKAZY",
    "odevzdane_obalky": "ODEVZDANE_OBALKY",
    "platne_listky": "PLATNE_LISTKY",
    "platne_hlasy": "PLATNE_HLASY",
}
STRANA = {
    "por": "POR_STR_HLAS_LIST",
    "vstrana": "VSTRANA",
    "hlasy": "HLASY",
    "hlasy_proc": "HLASY_PROC",
    "kandidatu": "KANDIDATU_POCET",
    "zastupitele": "ZASTUPITELE_POCET",
    "zastupitele_proc": "ZASTUPITELE_PROC",
}
ZASTUPITEL = {
    "poradi": "PORADOVE_CISLO",
    "hlasy": "HLASY",
    "hlasy_proc": "HLASY_PROC",
}


def parse_vysledek(el):
    ucast = el.find("kv:UCAST", NS)
    strany = []
    for s in el.findall("kv:VOLEBNI_STRANA", NS):
        strana = attrs(s, STRANA)
        strana["nazev"] = s.get("NAZEV_STRANY")
        zvoleni = []
        for z in s.findall("kv:ZASTUPITEL", NS):
            zast = attrs(z, ZASTUPITEL)
            zast.update(
                titul_pred=z.get("TITULPRED") or "",
                jmeno=z.get("JMENO"),
                prijmeni=z.get("PRIJMENI"),
                titul_za=z.get("TITULZA") or "",
            )
            zvoleni.append(zast)
        if zvoleni:
            strana["zvoleni"] = sorted(zvoleni, key=lambda z: z["poradi"])
        strany.append(strana)
    strany.sort(key=lambda s: s["por"])
    return {
        "ucast": attrs(ucast, UCAST) if ucast is not None else None,
        "strany": strany,
    }


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    if root.tag != f"{{{NS['kv']}}}VYSLEDKY_OBEC":
        raise ValueError(f"neočekávaný kořenový element {root.tag}")
    chyba = root.find("kv:CHYBA", NS)
    if chyba is not None:
        raise ValueError(f"CHYBA v XML: {chyba.text or ''} {dict(chyba.attrib)}")
    obec = root.find("kv:OBEC", NS)
    vysledek = obec.find("kv:VYSLEDEK", NS) if obec is not None else None
    if vysledek is None or vysledek.find("kv:UCAST", NS) is None:
        raise ValueError("XML neobsahuje OBEC/VYSLEDEK/UCAST")

    data = {
        "kod": obec.get("KODZASTUP"),
        "nazev": obec.get("NAZEVZAST"),
        "typ": obec.get("OZNAC_TYPU"),
        "voleno": num(obec.get("VOLENO_ZASTUP")),
        "pocet_obvodu": num(obec.get("POCET_OBVODU")),
        "je_spocteno": obec.get("JE_SPOCTENO") in ("1", "true"),
        "generovano": root.get("DATUM_CAS_GENEROVANI"),
        **parse_vysledek(vysledek),
    }
    obvody = []
    for o in obec.findall("kv:OBVOD", NS):
        obvod = {
            "cislo": num(o.get("CIS_OBVODU")),
            "voleno": num(o.get("VOLENO_ZASTUP")),
        }
        v = o.find("kv:VYSLEDEK", NS)
        if v is not None:
            obvod.update(parse_vysledek(v))
        obvody.append(obvod)
    if obvody:
        data["obvody"] = obvody
    return data


def download(url):
    last_err = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vysledkyvoleb/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except Exception as err:  # noqa: BLE001 - chceme zkusit znovu při jakékoli chybě
            last_err = err
            time.sleep(2 * (attempt + 1))
    raise last_err


def comparable(data):
    """Data bez časových údajů – generování se mění každou minutu i beze změny výsledků."""
    return {k: v for k, v in data.items() if k not in ("generovano", "stazeno")}


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def history_row(data, fetched):
    u = data["ucast"]
    return {
        "generovano": data["generovano"],
        "stazeno": fetched,
        "okrsky_zprac": u["okrsky_zprac"],
        "okrsky_celkem": u["okrsky_celkem"],
        "ucast_proc": u["ucast_proc"],
        "platne_hlasy": u["platne_hlasy"],
        "je_spocteno": data["je_spocteno"],
        "hlasy": {str(s["por"]): s["hlasy"] for s in data["strany"]},
        "zastupitele": {str(s["por"]): s["zastupitele"] for s in data["strany"]},
    }


def append_history(data_dir, data, fetched):
    hist_path = data_dir / "history" / f"{data['kod']}.jsonl"
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    with hist_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(history_row(data, fetched), ensure_ascii=False) + "\n")


def write_index(data_dir, config, updated):
    index = {"volby": config["volby"], "datum": config["datum"], "aktualizovano": updated, "obce": []}
    for obec in config["obce"]:
        d = load_json(data_dir / "latest" / f"{obec['kod']}.json")
        item = {"kod": obec["kod"], "nazev": obec["nazev"]}
        if d:
            item.update(
                voleno=d["voleno"],
                je_spocteno=d["je_spocteno"],
                okrsky_zprac=d["ucast"]["okrsky_zprac"],
                okrsky_celkem=d["ucast"]["okrsky_celkem"],
                generovano=d["generovano"],
            )
        index["obce"].append(item)
    write_json(data_dir / "index.json", index)


CONFIGS = ("config.json", "config-mesta.json", "config-praha.json")


def load_config():
    """Spojí seznamy obcí ze všech konfigurací (Brno + další města)."""
    config, seen = None, set()
    for name in CONFIGS:
        path = ROOT / name
        if not path.exists():
            continue
        c = json.loads(path.read_text(encoding="utf-8"))
        if config is None:
            config = {**c, "obce": []}
        for o in c["obce"]:
            if o["kod"] not in seen:
                seen.add(o["kod"])
                config["obce"].append(o)
    return config


def main():
    config = load_config()
    fetched = datetime.now(TZ).isoformat(timespec="seconds")
    changed, failed = [], []

    for obec in config["obce"]:
        kod = obec["kod"]
        url = URL.format(volby=config["volby"], datum=config["datum"], kod=kod)
        try:
            raw = download(url)
            data = parse(raw)
            if data["kod"] != kod:
                raise ValueError(f"XML je pro jiné zastupitelstvo ({data['kod']})")
        except Exception as err:  # noqa: BLE001
            print(f"CHYBA {kod} {obec['nazev']}: {err}", file=sys.stderr)
            failed.append(kod)
            continue

        latest_path = DATA / "latest" / f"{kod}.json"
        old = load_json(latest_path)
        if old is not None and comparable(old) == comparable(data):
            continue

        data["stazeno"] = fetched
        write_json(latest_path, data)
        (DATA / "raw").mkdir(parents=True, exist_ok=True)
        (DATA / "raw" / f"{kod}.xml").write_bytes(raw)
        append_history(DATA, data, fetched)
        u = data["ucast"]
        print(f"ZMĚNA {kod} {data['nazev']}: okrsky {u['okrsky_zprac']}/{u['okrsky_celkem']}")
        changed.append(kod)

    if changed or not (DATA / "index.json").exists():
        write_index(DATA, config, fetched)

    print(f"Hotovo: změněno {len(changed)}, chyb {len(failed)}, celkem {len(config['obce'])}")
    if failed and len(failed) == len(config["obce"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
