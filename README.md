# Výsledky voleb – KV 2026

Průběžné výsledky voleb do zastupitelstev obcí (9.–10. 10. 2026) pro Brno
a 15 městských částí, s přibližným výpočtem mandátů a skládáním koalic.

**Web:** https://michalberg.github.io/vysledkyvoleb/ (Brno)
a https://michalberg.github.io/vysledkyvoleb/praha.html (Praha + MČ Praha 1–22)
a https://michalberg.github.io/vysledkyvoleb/mesta.html (Města 1)
a https://michalberg.github.io/vysledkyvoleb/mesta2.html (Města 2)

Zdroj: otevřená data [volby.gov.cz](https://volby.gov.cz/opendata/kv2026/KV2026_XML.htm).

## Web

Statická stránka bez buildu (`index.html`, `app.js`, `app.css`, `fonts/`)
na GitHub Pages. Design: varianta 1c ze zadání v `design_handoff_volebni_vysledky/`
(lokálně, není v repozitáři).

**Projektor (od 700 px šířky)** – plátno 1024 × 768 škálované na obrazovku:

- automatická rotace Brno → 15 MČ (výchozí 12 s), kliknutím na celek v levém
  sloupci se přepne ručně,
- graf stran nad 3 % plus vždy naše kandidátka (u Brna všechny strany,
  u MČ přepínač „Všechny strany“),
- režim „Sestavit koalici“ – zastaví rotaci, výběr stran se pamatuje
  pro každý celek zvlášť (`localStorage`),
- výchozí světlý režim, volba tmavého se ukládá v prohlížeči.

**Mobil (pod 700 px)** – všechny celky pod sebou, vodorovné pruhy s plnými
názvy, koalice v celoobrazovkovém panelu.

**Data na stránce:**

- každou minutu živé XML z volby.gov.cz (server povoluje CORS),
  při výpadku záloha `data/latest/` a u času aktualizace ⚠,
- celek bez sečteného okrsku ukazuje šedě výsledky 2022 (`mock/2022/`),
- mandáty jsou do sečtení všech okrsků přibližný výpočet dle současných
  výsledků podle § 45 zákona 491/2001 Sb.: 5% klauzule (u neúplné kandidátky
  ze sníženého základu, při méně než dvou stranách se snižuje na 4–1 %),
  D'Hondt, strop počtem kandidátů. Na konečných výsledcích 2022 dává
  u všech 16 zastupitelstev přesně oficiální mandáty. Po sečtení se
  zobrazí oficiální mandáty z XML.
- mandáty se ukazují číslem s ikonou postavy, nula se nezobrazuje.

**URL parametry:**

| Parametr | Význam |
|---|---|
| `?demo` | vymyšlené hlasy pro letošní kandidátky (test barev a rozložení; Jundrov bez dat) |
| `?mock=2022` | konečné výsledky 2022 |
| `?mock=2022-prubeh` | stav 2022 uprostřed sčítání |
| `?interval=12` | délka rotace v sekundách |

GitHub Pages posílá `max-age=600`; `app.js` a `app.css` se proto načítají
s časovým parametrem, aby se změny projevily hned. Samotné `index.html`
může prohlížeč držet až 10 minut (Cmd + Shift + R).

## Dvě stránky

| Stránka | Konfigurace | Obsah |
|---|---|---|
| `index.html` | `config.json` (`hlavni: true`) | Brno + 15 MČ; Brno má řádek nahoře a ukazuje všechny strany |
| `praha.html` | `config-praha.json` (`hlavni: true`, `hlavni_vsechny_strany: false`) | Praha + 22 MČ; Praha nahoře, strany nad 3 % |
| `mesta.html` | `config-mesta.json` | Brno, Praha, Praha 1, Praha 3, Vsetín, Opava, Nový Jičín, Jablonec n. N., Prostějov, Jeseník, Tábor, Příbram, Mladá Boleslav, Třebíč, Liberec |
| `mesta2.html` | `config-mesta2.json` | Česká Lípa, České Budějovice, Hradec Králové, Cheb, Chomutov, Klášterec n. O., Litoměřice, Litvínov, Lovosice, Mníšek p. B., Most, Náchod, Olomouc, Ostrava-Mariánské Hory a Hulváky, Pardubice, Písek, Plzeň, Telč, Teplice, Ústí n. L. |

Obě stránky sdílejí `app.js`; stránka si konfiguraci bere z `<body data-config>`.
Stahovací skript čte všechny konfigurace a ukládá všechno do `data/`.

## Konfigurace

| Soubor | Obsah |
|---|---|
| `config.json`, `config-mesta.json` | volby, datum, interval rotace, `nadpis` levého sloupce a seznam celků: `kod` (KODZASTUP), `zobrazit`, `kratky` (levý sloupec), `nase` (číslo naší kandidátky pro 2026 a 2022), `odkaz` |
| `barvy.json` | barevné skupiny stran; barva kandidátky podle výjimky `"KODZASTUP:číslo"`, jinak podle kódu VSTRANA, jinak `vychozi`; volitelně `barva_tmava` pro tmavý režim |
| `zkratky.json` | krátké názvy kandidátek do grafu (klíč = přesný oficiální název), plný název je v tooltipu |
| `strany.json` | číselník stran (VSTRANA → název, zkratka, typ, složení koalice), generuje `scripts/ciselnik.py` |

Naše kandidátka je vždy `#0bd26f`; ostatní kandidátky ze zelené skupiny
se zobrazují šedě, aby se s ní nepletly.

Odkazy na volby.gov.cz (`odkaz`) zatím vedou na přehled výsledků – letošní
prezentace běží v nové aplikaci a odkazy ve tvaru z roku 2022 nefungují.

## Stahování dat

1. [cron-job.org](https://cron-job.org) každou minutu spustí workflow
   `.github/workflows/fetch.yml` přes GitHub API (úlohy na so 10. 10. 14–24 h
   a ne 11. 10. 0–12 h).
2. Workflow spustí `scripts/fetch.py`, který stáhne XML
   `vysledky_obec_<KODZASTUP>.xml` pro každé zastupitelstvo.
3. Pokud se výsledky změnily, uloží je do `data/` a commitne.
   Při nedostupnosti volby.gov.cz zůstávají poslední uložená data.

Záložně se workflow spouští i vestavěným cronem GitHubu každých 5 minut.

| Soubor | Obsah |
|---|---|
| `data/index.json` | přehled zastupitelstev a stav sčítání |
| `data/latest/<kod>.json` | aktuální výsledek: účast, strany, hlasy, počty kandidátů, po sečtení mandáty a zvolení |
| `data/history/<kod>.jsonl` | jeden řádek na každou změnu (hlasy stran v čase) |
| `data/raw/<kod>.xml` | poslední stažené XML |

### Nastavení cron-job.org

1. **GitHub token:** Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token
   - Repository access: *Only select repositories* → `vysledkyvoleb`
   - Permissions → Repository → **Actions: Read and write**
2. **cron-job.org** → Create cronjob
   - URL: `https://api.github.com/repos/michalberg/vysledkyvoleb/actions/workflows/fetch.yml/dispatches`
   - Request method: **POST**
   - Headers:
     - `Accept: application/vnd.github+json`
     - `Authorization: Bearer <TOKEN>`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `Content-Type: application/json`
   - Request body: `{"ref":"main"}`
   - Úspěšná odpověď je `204 No Content`.

Lokální soubor `token.md` s klíči je v `.gitignore`.

## Mock data z voleb 2022

V `mock/` jsou výsledky stejných zastupitelstev z roku 2022 ve stejném
formátu jako `data/`:

| Adresář | Stav |
|---|---|
| `mock/2022/` | konečný stav, oficiální mandáty a zvolení; slouží i jako šedé zobrazení celků bez dat |
| `mock/2022-prubeh/` | uprostřed sčítání (Brno 178/352 okrsků), bez mandátů |

Konečné výsledky (názvy, hlasy, mandáty, zvolení) jsou z registru KV 2022
na opendata volby.gov.cz, účast a průběh z okrskových dávek 2022 – historie
tak odpovídá skutečnému průběhu sčítání. Generuje `python3 scripts/mock2022.py`
(dávky a registr se ukládají do `.cache/`). Kandidátky 2022 mají jiné kódy VSTRANA,
takže barvy v mock režimu neodpovídají – pro test barev slouží `?demo`.

## Lokální spuštění

```sh
python3 scripts/fetch.py          # stažení aktuálních výsledků do data/
python3 -m http.server 8000       # web na http://localhost:8000/
```

Stačí standardní knihovna Pythonu 3.9+.
