# Warsaw Public Transport Open Data API (`api.um.warszawa.pl`)

> Practical reference for the ZTM/WTP public-transport endpoints, **verified live on 2026-06-28** against
> token `e2022fe8-…`. Where the live behaviour differs from the official docs or community examples,
> the **live behaviour wins** and is noted as such.

This is the canonical, first-party, public data source for Warsaw public-transport data — the official
ZTM/WTP feed that downstream consumer apps ultimately derive from.

---

## 1. Conventions

- **Base URL:** `https://api.um.warszawa.pl/api/action/<action>/`
- **Style:** CKAN-derived. Every call is `GET` with query params. The dataset is selected by either
  `resource_id` or `id` (the API is inconsistent — see each endpoint).
- **Auth:** every call needs `&apikey=<TOKEN>`.
- **Always URL-encode** Polish characters (`ł`, `ż`, `ó`, …). Prefer `curl -G --data-urlencode`.
- **Response envelope:** always `{"result": …}`.
  - Success → `result` is an array or object.
  - **Errors are returned as HTTP 200** with `result` set to a human string, e.g.
    `"Błędna metoda lub parametry wywołania"` (bad method/params) or
    `"Błędny apikey lub jego brak"` (bad/missing key). **There is no error status code** — you must
    inspect `result`.
  - "No data" is `"result": null`.
- **Key–value rows:** the `dbtimetable_get` endpoints do **not** return plain objects. Each row is a
  list of `{"key":…, "value":…}` pairs that you must fold into a dict yourself:
  ```python
  row = {kv["key"]: kv["value"] for kv in entry["values"]}   # lines endpoint
  row = {kv["key"]: kv["value"] for kv in entry}             # departures endpoint (no "values" wrapper)
  ```

---

## 2. Endpoint catalog (quick reference)

| # | Capability | action | dataset id (param) | Key params | Verified |
|---|------------|--------|--------------------|------------|----------|
| 1 | **Live vehicle GPS** (buses & trams) | `busestrams_get` | `resource_id=f2e5503e-927d-4ad3-9500-4ab9e55deb59` | `type` (1=bus, 2=tram), `line`*, `brigade`* | ✅ works |
| 2 | **Lines stopping at a stop post** | `dbtimetable_get` | `id=88cd555f-6f31-43ca-9de4-66c479ad5942` | `busstopId`, `busstopNr` | ✅ works |
| 3 | **Scheduled departures** (stop+post+line) | `dbtimetable_get` | `id=e923fa0e-d96c-43f9-ae6e-60518c9f3238` | `busstopId`, `busstopNr`, `line` | ✅ works |
| 4 | **Stop group by name → posts + coords** | `dbtimetable_get` | `id=b27f4c17-5c50-4a5b-89dd-236b282bc499` | `name` | ⚠️ returns `null` (see §6) |
| 5 | **Route definitions** (line → variant → stop sequence) | `public_transport_routes` | *(none)* | — | ✅ works |
| 6 | **Dictionary** (streets, stop-group names, stop types) | `public_transport_dictionary` | *(none)* | — | ✅ works |
| 7 | **Vector-map POI layers** (metro entrances, cycle, parking…) | `wfsstore_get` | `id=<layer-uuid>` | optional `bbox`, `circle`, `filter`, `limit` | ✅ works |
| 8 | Stop list w/ coordinates (`dbstore_get`, `ab75c33d-…` / `1c08a38c-…`) | `dbstore_get` | *(all ids dead)* | — | ❌ decommissioned (see §7) |
| 9 | Live trams (legacy `wsstore_get` `c7238cfe-…`) | `wsstore_get` | — | — | ❌ deprecated, rejected |

\* `line` / `brigade` are **accepted but currently ignored** by the server — see §3.

---

## 3. Live vehicle positions — `busestrams_get`  ✅ core endpoint

```
GET /api/action/busestrams_get/
    ?resource_id=f2e5503e-927d-4ad3-9500-4ab9e55deb59
    &type=2            # 1 = bus, 2 = tram   (REQUIRED in practice)
    &apikey=<TOKEN>
    # &line=20 &brigade=1   <-- accepted but IGNORED (see note)
```

**Response** — array of vehicle objects:

```json
{ "result": [
  { "Lines": "28", "Brigade": "014", "VehicleNumber": "1284",
    "Lat": 52.29962, "Lon": 20.931208, "Time": "2026-06-28 21:09:13" }
]}
```

| Field | Meaning |
|-------|---------|
| `Lines` | line number/symbol (e.g. `28`, `151`, `N25`) |
| `Brigade` | brigade (vehicle duty) number — combine with `Lines` to identify a run |
| `VehicleNumber` | physical vehicle id |
| `Lat`, `Lon` | WGS84 position |
| `Time` | timestamp of **last GPS report**, `YYYY-MM-DD HH:MM:SS`, local Warsaw time |

### Verified behaviour & gotchas (live, 2026-06-28)
- **`type` is effectively required.** type=1 returned **1082 buses**; type=2 returned **237 trams**.
- **`line` and `brigade` are IGNORED.** `type=1` alone, `&line=523`, and `&line=523&brigade=1` all
  returned the identical full set of 1082 vehicles of every line. → **Filter client-side** by `Lines`.
- **The feed contains stale "ghost" vehicles.** Of 237 trams, only **152 had a `Time` within the last
  2 minutes**; the rest were hours-to-months old (e.g. `2024-10-26`, `2026-06-19`) — vehicles that
  stopped reporting but linger in the feed. **Always drop rows whose `Time` is older than ~60–120 s**
  (this is exactly what the `next-ztm` reference does: `time > now-60000`).
- No bounding-box parameter — you get the whole city and clip locally.
- Refresh cadence is ~10–20 s server-side; don't poll faster.

```bash
curl -sG 'https://api.um.warszawa.pl/api/action/busestrams_get/' \
  --data-urlencode 'resource_id=f2e5503e-927d-4ad3-9500-4ab9e55deb59' \
  --data-urlencode 'type=2' --data-urlencode "apikey=$KEY"
```

---

## 4. Timetables — `dbtimetable_get`

Three distinct datasets share this action; the `id` selects which. A **stop is addressed by a pair**:
`busstopId` (4-digit *zespół* / stop-group id, called `nr_zespolu` elsewhere) + `busstopNr`
(2-char post number, e.g. `01`, `04`).

### 4a. Lines at a stop post — `id=88cd555f-6f31-43ca-9de4-66c479ad5942`  ✅
```
?id=88cd555f-6f31-43ca-9de4-66c479ad5942&busstopId=7009&busstopNr=01&apikey=<TOKEN>
```
Returns one row per line; fold `values`:
```json
{ "result": [ { "values": [ { "key": "linia", "value": "151" } ] }, … ] }
```
→ `["151","143","182","525","520","187","523","188","138","502","514","N25"]`

### 4b. Scheduled departures — `id=e923fa0e-d96c-43f9-ae6e-60518c9f3238`  ✅
```
?id=e923fa0e-d96c-43f9-ae6e-60518c9f3238&busstopId=7009&busstopNr=01&line=151&apikey=<TOKEN>
```
Returns the full **day timetable** (planned, not live) — one row per scheduled departure:

| key | example | meaning |
|-----|---------|---------|
| `czas` | `20:37:00` | scheduled departure time. **Can exceed 24h** (e.g. `25:30:00` = 01:30 next day) — parse defensively |
| `kierunek` | `Rechniewskiego` | direction / headsign |
| `brygada` | `1` | brigade — **join key to match the live `Brigade` from §3** |
| `trasa` | `TP-REH` | route variant code (see §5) |
| `symbol_1`, `symbol_2` | `null` | footnote symbols (accessibility etc.), usually null |

Rows come as a bare list of key/value pairs (no `values` wrapper):
```python
dep = {kv["key"]: kv["value"] for kv in entry}
```

> **There is no official "live ETA" endpoint.** Real-time arrival predictions (as shown on live
> departure boards) are
> computed by joining **scheduled departures (4b)** with **live GPS (§3)** via `(line, brigade)`. We must
> do that join ourselves.

---

## 5. Route definitions — `public_transport_routes`  ✅
```
?apikey=<TOKEN>          # no id/resource_id
```
Nested object: **line → route-variant code → stop-sequence index → stop descriptor**:
```json
{ "result": { "217": { "TX-WIL02": {
   "11": { "ulica_id":"1991", "nr_zespolu":"3040", "typ":"1", "nr_przystanku":"02", "odleglosc":422 }
}}}}
```
| field | meaning |
|-------|---------|
| `nr_zespolu` | stop-group id (= `busstopId`) |
| `nr_przystanku` | post number (= `busstopNr`) |
| `ulica_id` | street id → resolve via dictionary `ulice` |
| `typ` | stop type → resolve via dictionary `typy_przystankow` (`1` stały, `2` na żądanie, `3` krańcowy) |
| `odleglosc` | distance (m) from route start |
| variant key (`TP-REH`, `TX-WIL02`) | matches `trasa` in 4b |

Use this to draw a line's path and list its stops in order.

---

## 6. Dictionary — `public_transport_dictionary`  ✅
```
?apikey=<TOKEN>          # no id/resource_id
```
Top-level keys (verified): **`ulice`**, **`typy_przystankow`**, **`zespoly_przystankowe`**, **`miejsca`**.
```json
{ "result": {
  "ulice": { "2318": "Kleszczowa", … },
  "typy_przystankow": { "1": "stały", "2": "na żądanie", "3": "krańcowy" },
  "zespoly_przystankowe": { "4026": "Paluch", "4027": "CH  Blue City", … },
  "miejsca": { "344": "Chojnów", … }
}}
```
**`zespoly_przystankowe` is our name↔id map** (stop-group id → human name). Because the live name-search
endpoint (§6/​#4) is broken, **resolve a stop name to a `busstopId` by searching this dictionary
client-side**, then call 4a/4b.

### ⚠️ The name-search resource `b27f4c17-…` returns `null`
The officially-documented "get stop group by name" call
(`dbtimetable_get?id=b27f4c17-5c50-4a5b-89dd-236b282bc499&name=…`) **returned `null` for every query
tested** — `Sady`, `Sady Żoliborskie`, `Marszałkowska`, `Metro Młociny`, `Siekierkowska` (the docs' own
example), with and without trailing slash, with proper URL-encoding, with exact dictionary names
(`Paluch`, `Kabaty`), and with `busstopId=`/`size=`. The key is valid (other `dbtimetable_get`
datasets work, and a bad key returns a *different* error — see §9), so this dataset is
**server-side broken/decommissioned** — a long-standing, widely-reported issue.
It is nonetheless the resource **both** `pywarsaw` (`get_stop_set`) and `warsaw-data-api`
(`get_bus_stop_id_by_bus_stop_name`) still target. When it worked, it returned these raw key/value
fields — and was the **per-post coordinate source**:
`zespol`, `slupek`, `nazwa_zespolu`, `id_ulicy`, **`szer_geo`** (lat), **`dlug_geo`** (lon),
`kierunek`, `obowiazuje_od`.
**Workaround today:** dictionary (`zespoly_przystankowe`) for name→id, `public_transport_routes` for
the stop's sequence/membership; for coordinates see §7.

---

## 7. Vector-map POI layers (`wfsstore_get`) ✅  +  stop coordinates ❌

### 7a. `wfsstore_get` — WFS point layers ✅ works
Note the action is **`wfsstore_get`** (WFS), not the legacy `wsstore_get`.
```
?id=<layer-uuid>&apikey=<TOKEN>        # optional: bbox, circle, filter, limit
```
Response shape (verified) — geometry + key/value properties:
```json
{ "result": {
  "featureMemberPropertyKey": ["OBJECTID","LOKALIZACJA","NR_STACJI","ROWERY","STOJAKI","AKTU_DAN"],
  "featureMemberList": [
    { "geometry": { "type":"ShapePoint",
        "coordinates":[{"latitude":"52.207419","longitude":"21.047962"}] },
      "properties": [ {"key":"OBJECTID","value":"2585791"},
                      {"key":"LOKALIZACJA","value":"Czerniakowska - Gagarina"}, … ] }
  ]
}}
```
| Layer | id (verified live ✅ unless noted) | property keys |
|-------|------------------------------------|---------------|
| **Metro/subway entrances** | `0ac7f6d1-a26b-430f-9e3d-a41c5356b9a3` | `OBJECTID` |
| **Veturilo cycle stations** | `a08136ec-1037-4029-9aa5-b0d0ee0b9d88` | `OBJECTID, LOKALIZACJA, NR_STACJI, ROWERY, STOJAKI, AKTU_DAN` |
| Cycle tracks | `8a235d27-b96a-4876-9b92-9e164940c9b6` | location, route_type, district, surface |
| Parking lots | `157648fd-a603-4861-af96-884a8e35b155` | car/disabled/motorcycle places, name |
| Theaters | `e26218cb-61ec-4ccb-81cc-fd19a6fee0f8` | address/contact fields |

(Occasionally returns `"Wfs error: Connection reset"` — transient upstream WFS hiccup; just retry.)
No **bus/tram stop** WFS layer and no **tram-track** layer exists in any known wrapper.

### 7b. Stop coordinates ❌ — currently unavailable via the API
Every documented "stops with coordinates" dataset is **decommissioned** (all return
`"Błędna metoda lub parametry wywołania"`, with `id=` or `resource_id=`, slash or no slash, with
`page`/`size`):
- `dbstore_get` `ab75c33d-3a26-4342-b36a-6e5fef0a3ac3` (full list)
- `dbstore_get` `1c08a38c-ae09-46d2-8926-4f9d25cb0630` (current-day list) ← note: pywarsaw still
  references both, but they **no longer work** against the live API
- `wsstore_get` `c7238cfe-8b1f-4c38-bb4a-de386db7e776` (legacy live trams)

And the `b27f4c17` name-search (the other coordinate source, fields `szer_geo`/`dlug_geo`) returns
`null` (§6).

**So the API does not currently serve per-stop lat/lon.** Practical options for our project:
1. **GTFS static feed** from WTP (`stops.txt` has `stop_id, stop_lat, stop_lon`) — the reliable source
   for stop geometry; refresh weekly. Join its stop ids to the API's `busstopId`/`busstopNr`.
2. Derive stop *membership/order* from `public_transport_routes` (gives `nr_zespolu` + `nr_przystanku`
   per line) and attach coordinates from the GTFS `stops.txt`.
3. For non-stop POIs (metro entrances, bikes, parking) use `wfsstore_get` (§7a), which **does** return
   coordinates.

---

## 8. Recommended client architecture for our project
1. **Bootstrap (cache for a day):** `public_transport_dictionary` (names, streets, types) +
   `public_transport_routes` (line paths & stop sequences). These are large and static-ish.
2. **Stop board:** `dbtimetable_get` 4a (lines) → 4b (scheduled departures per line).
3. **Live layer:** poll `busestrams_get` (`type=1` and `type=2`) every ~15 s; **drop stale rows by
   `Time`**, filter to lines/area client-side.
4. **Live ETA:** join 4b × live GPS on `(Lines/line, Brigade/brygada)` to compute predicted arrivals,
   since the API has no native prediction endpoint.

## 9. Error handling cheat-sheet
All responses are **HTTP 200**; detect failure by inspecting the body.

| body | meaning |
|------|---------|
| `{"result": [...]}` / `{"result": {...}}` | success |
| `{"result": null}` | query OK, no matching data |
| `{"result": "Błędna metoda lub parametry wywołania"}` | wrong action/dataset id or missing/invalid params |
| `{"result": "false", "error": "Błędny apikey lub jego brak"}` | bad or missing `apikey` (note the extra `error` field) |
| `{"result": "Wfs error: Connection reset"}` | transient `wfsstore_get` upstream error — retry |

## 10. Closing the coordinate gap — GTFS `stops.txt` join ✅ verified

Since the API no longer serves per-stop lat/lon (§7b), get it from the official **WTP GTFS** feed and
join on stop id. **Verified live 2026-06-28** against the feed + API.

- **Feed (practical):** `https://mkuran.pl/gtfs/warsaw.zip` — community-generated GTFS, rebuilt daily
  (~97 MB). Use `stops.txt`. Columns: `stop_id, stop_name, stop_code, platform_code, stop_lat,
  stop_lon, location_type, parent_station, …, street_name, town_name`.
- **Sources:**
  - Generated from official ZTM data by the open-source converter
    [`MKuranowski/WarsawGTFS`](https://github.com/MKuranowski/WarsawGTFS).
  - **Official upstream:** ZTM schedule data at
    `https://www.ztm.waw.pl/pliki-do-pobrania/dane-rozkladowe/` — authoritative but in ZTM's
    *proprietary* text format, **not** GTFS (that's what WarsawGTFS converts).
  - Aggregator mirror: Transitland feed `f-u3q-warszawski~transport~publiczny`.

### The join rule
```
GTFS stop_id  ==  busstopId (4 digits, zero-padded)  +  busstopNr (2 chars)
```
- `busstopId=7009, busstopNr=01` ⇄ `stop_id "700901"` → **Marszałkowska, (52.217931, 21.020112)**.
- Reverse: `busstopId = stop_id[:4]`, `busstopNr = stop_id[4:6]`.
- Round-trip confirmed: GTFS `100101` → `1001`/`01` → API lines-at-stop returns `146,147,202,N71,…` ✅

### Which stop_ids the rule covers (feed has 7166 rows; 6745 are bus/tram posts)
| `stop_id` shape | `location_type` | meaning | join? |
|-----------------|-----------------|---------|-------|
| 6-digit numeric (e.g. `700901`) | 0 | **bus/tram/SKM stop post** | ✅ `[:4]`+`[4:6]` |
| 4-digit numeric (e.g. `1901`) | 0 | rail station node (no post), e.g. *Warszawa Zoo* | ✗ no busstopNr |
| 5-char `####M` (e.g. `1003M`) | 1 | metro **station** parent | ✗ separate scheme |
| `####M:E#` / `####M:P#` (e.g. `1003M:E1`) | 2 | metro **entrance / platform** | ✗ |

Only the 6-digit numeric posts are addressable by the API's `busstopId`/`busstopNr` — exactly the
network `busestrams_get` (`type=1`/`2`) and `dbtimetable_get` operate on. Metro/rail nodes use the
`M`-suffixed ids and aren't part of the bus/tram timetable pair.

### Helper
`scripts/gtfs_stops_join.py` builds both indexes from `stops.txt`:
```python
from scripts.gtfs_stops_join import load_stop_index, gtfs_id, split_id
by_id, by_zespol = load_stop_index("stops.txt")   # 6745 posts / 2770 groups
by_id["700901"].lat, by_id["700901"].lon          # -> 52.217931, 21.020112
gtfs_id("7009", "1")                              # -> "700901"  (note zero-pad)
split_id("700901")                                # -> ("7009", "01")
```
**Pipeline:** cache `stops.txt` (refresh weekly) → for any API stop, `gtfs_id(busstopId, busstopNr)`
gives coordinates + canonical name/street; for `public_transport_routes` output use
`nr_zespolu`+`nr_przystanku` the same way.

---

## 11. Caveats from cross-checking community wrappers
- **Malformed UUID in the wild:** `warsaw-data-api` ships a broken `busestrams` id
  `f2e5503e927d-4ad3-9500-4ab9e55deb59` (missing a hyphen). Use the correct
  `f2e5503e-927d-4ad3-9500-4ab9e55deb59` (pywarsaw).
- `public_transport_routes` / `public_transport_dictionary` are **not** wrapped by any of the four
  surveyed libraries (pywarsaw, warsaw-data-api, ztm_warszawa, WAWUMAPI) — they're official actions we
  verified live here directly, so treat this doc as their primary reference.
- pywarsaw is the most complete/authoritative wrapper for UUIDs; prefer it where sources disagree.

---

## 12. Limits & polling policy

**UM Warsaw does NOT specify any API rate limit or quota.** Verified 2026-06-28 three ways:
- The official portal (`api.um.warszawa.pl`) and the API guide
  (`um.warszawa.pl/waw/granty/most-danych-poradnik-api`) state **no** rate limit, request quota,
  per-key cap, or polling-frequency rule. The "Warunki korzystania z danych" terms cover data
  **licensing/attribution**, not request rates.
- **No rate-limit headers** are returned (`X-RateLimit-*`, `Retry-After`, quota — all absent). The only
  notable header is a BIG-IP/F5 anti-bot cookie (`TS01…`) → there is a **load-balancer-level abuse
  filter**, not a published per-key quota.
- **Burst test:** 25 concurrent `busestrams_get` calls all returned `200` in ~0.2–0.4 s — no `429`,
  no throttling.

**Implications**
- No enforced per-key quota at normal volumes. The free key is self-registered and, per the terms,
  can be **revoked for abuse** — the real constraint is "don't hammer it," not a number.
- Polling faster than the source refresh is pointless: live GPS updates server-side only every
  ~10–20 s; timetables/routes/dictionary are effectively static.
- The undocumented BIG-IP layer *can* block a single IP that bursts aggressively (this is what bites
  scrapers). Stay well under it with backoff.

**Self-imposed cadence for this project**
| Data | Cadence |
|------|---------|
| `busestrams_get` (live GPS) | every **15–20 s** per `type` (matches refresh) |
| `dbtimetable_get` departures / lines | on demand; cache a few minutes |
| `public_transport_routes`, `public_transport_dictionary`, GTFS `stops.txt` | once per **day** (cache) |

- Use **one shared HTTP client** (don't fan out many IPs/keys).
- **Retry with backoff** on transient failures: `"Wfs error: Connection reset"` and any non-200.
- Remember errors are HTTP 200 — gate ret/parse on the `result` body (§9), not status code.
