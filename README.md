# Výsledky voleb – KV 2026

Průběžné stahování výsledků voleb do zastupitelstev obcí (9.–10. 10. 2026)
z otevřených dat [volby.gov.cz](https://volby.gov.cz/opendata/kv2026/KV2026_XML.htm)
pro zastupitelstva uvedená v `config.json`.

## Web

`index.html` + `app.js` + `app.css`, statická stránka bez buildu (GitHub Pages).

- Projektor 4:3 (od 700 px šířky): rotace Brno → 15 MČ, režim „Sestavit koalici“.
- Mobil (pod 700 px): všechny celky pod sebou, koalice v panelu.
- Data: živé XML z volby.gov.cz, při výpadku záloha `data/latest/`.
- Celek bez sečteného okrsku ukazuje šedě výsledky 2022.
- Mandáty do sečtení všech okrsků odhaduje podle § 45 zákona 491/2001 Sb.
  (5% klauzule s úpravou pro neúplné kandidátky, D'Hondt, strop počtem kandidátů).
- URL parametry: `?mock=2022` / `?mock=2022-prubeh` (testovací data), `?interval=12` (rotace v s).
- Naše kandidátka pro každý celek je v `config.json` → `nase` (číslo kandidátní listiny).

## Jak to funguje

1. [cron-job.org](https://cron-job.org) každou minutu spustí workflow
   `.github/workflows/fetch.yml` přes GitHub API.
2. Workflow spustí `scripts/fetch.py`, který stáhne XML
   `vysledky_obec_<KODZASTUP>.xml` pro každé zastupitelstvo.
3. Pokud se výsledky změnily, uloží je do `data/` a commitne.
   Při nedostupnosti volby.gov.cz zůstávají poslední uložená data.

Záložně se workflow spouští i vestavěným cronem GitHubu každých 5 minut.

## Data

| Soubor | Obsah |
|---|---|
| `data/index.json` | přehled zastupitelstev a stav sčítání |
| `data/latest/<kod>.json` | aktuální výsledek: účast, strany, hlasy, počty kandidátů, po sečtení mandáty a zvolení |
| `data/history/<kod>.jsonl` | jeden řádek na každou změnu (hlasy stran v čase) |
| `data/raw/<kod>.xml` | poslední stažené XML |

## Strany a barvy

- `strany.json` – číselník volebních stran (kód VSTRANA → název, zkratka,
  typ, složení koalice) pro sledovaná zastupitelstva. Generuje
  `python3 scripts/ciselnik.py` z číselníků volby.gov.cz.
- `barvy.json` – barevné skupiny. Barva kandidátky se určí podle výjimky
  `"KODZASTUP:číslo kandidátky"`, jinak podle kódu VSTRANA, jinak `vychozi`.

## Mock data z voleb 2022

Pro vývoj frontendu před ostrými daty jsou v `mock/` výsledky stejných
zastupitelstev z roku 2022 ve stejném formátu jako `data/`:

| Adresář | Stav |
|---|---|
| `mock/2022/` | konečný stav, všechno sečteno, oficiální mandáty a zvolení |
| `mock/2022-prubeh/` | uprostřed sčítání (Brno 178/352 okrsků), bez mandátů |

Historie (`history/*.jsonl`) je zrekonstruovaná z okrskových dávek 2022,
takže odpovídá skutečnému průběhu sčítání. Generuje se skriptem
`python3 scripts/mock2022.py`.

## Nastavení cron-job.org

1. **GitHub token:** Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token
   - Repository access: *Only select repositories* → `vysledkyvoleb`
   - Permissions → Repository → **Actions: Read and write**
2. **cron-job.org** → Create cronjob
   - URL: `https://api.github.com/repos/michalberg/vysledkyvoleb/actions/workflows/fetch.yml/dispatches`
   - Schedule: every minute
   - Advanced → Request method: **POST**
   - Headers:
     - `Accept: application/vnd.github+json`
     - `Authorization: Bearer <TOKEN>`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `Content-Type: application/json`
   - Request body: `{"ref":"main"}`
   - Úspěšná odpověď je `204 No Content`.

## Lokální spuštění

```sh
python3 scripts/fetch.py
```

Stačí standardní knihovna Pythonu 3.9+.
