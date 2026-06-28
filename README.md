# Warsaw Public Transport Open Data API — Unofficial Guide & OpenAPI Spec

A practical, **field-verified** guide to the public-transport endpoints of the City of
Warsaw open-data API (**`api.um.warszawa.pl`**) — the official ZTM/WTP feed behind live
bus & tram positions, timetables, and route maps.

The official docs are sparse and partly out of date. Everything here was **tested live
against the API** (last verified **2026-06-28**); where the API's real behaviour differs
from its docs, this guide documents reality and says so.

> ⚠️ **Unofficial.** Not affiliated with m.st. Warszawa or ZTM/WTP. Data © m.st. Warszawa,
> used under the portal's *Warunki korzystania z danych*.

## 📚 What's here

| File | What it is |
|------|-----------|
| **[`openapi.yaml`](openapi.yaml)** | OpenAPI 3.1 spec (lints clean; use in Swagger Editor, Postman, codegen) |
| **[`docs/warszawa-api.md`](docs/warszawa-api.md)** | The deep reference — every endpoint, field, quirk, error string |
| **[`docs/index.html`](docs/index.html)** | Rendered API docs (Redoc) for **GitHub Pages** |
| **[`scripts/gtfs_stops_join.py`](scripts/gtfs_stops_join.py)** | Stop coordinates via the GTFS join (see below) |

📖 **Rendered API docs:** <https://tajchert.github.io/warsaw-transport-api/>  ← _enable Pages → Branch `main` / `/docs` (see [Publishing](#-publishing-on-github))._

## 🚀 Quick start

1. Get a free API key — register at <https://api.um.warszawa.pl/>.
2. Every call is `GET https://api.um.warszawa.pl/api/action/<action>/?…&apikey=<KEY>`.

```bash
KEY=your-key-here

# Live tram positions (type=1 bus, type=2 tram)
curl -sG 'https://api.um.warszawa.pl/api/action/busestrams_get/' \
  --data-urlencode 'resource_id=f2e5503e-927d-4ad3-9500-4ab9e55deb59' \
  --data-urlencode 'type=2' --data-urlencode "apikey=$KEY"

# Lines serving stop 7009 / post 01 (Marszałkowska)
curl -sG 'https://api.um.warszawa.pl/api/action/dbtimetable_get/' \
  --data-urlencode 'id=88cd555f-6f31-43ca-9de4-66c479ad5942' \
  --data-urlencode 'busstopId=7009' --data-urlencode 'busstopNr=01' \
  --data-urlencode "apikey=$KEY"

# Scheduled departures for one line at that post
curl -sG 'https://api.um.warszawa.pl/api/action/dbtimetable_get/' \
  --data-urlencode 'id=e923fa0e-d96c-43f9-ae6e-60518c9f3238' \
  --data-urlencode 'busstopId=7009' --data-urlencode 'busstopNr=01' \
  --data-urlencode 'line=151' --data-urlencode "apikey=$KEY"
```

> 💡 Always `--data-urlencode` — Polish characters (`ł`, `ż`, `ó`…) must be encoded.

## 🧭 Endpoints at a glance

| Capability | action | dataset id | Status |
|-----------|--------|-----------|:------:|
| Live bus/tram GPS | `busestrams_get` | `resource_id=f2e5503e-927d-4ad3-9500-4ab9e55deb59` | ✅ |
| Lines at a stop post | `dbtimetable_get` | `id=88cd555f-6f31-43ca-9de4-66c479ad5942` | ✅ |
| Scheduled departures | `dbtimetable_get` | `id=e923fa0e-d96c-43f9-ae6e-60518c9f3238` | ✅ |
| Route topology | `public_transport_routes` | *(none)* | ✅ |
| Dictionary (names/streets/types) | `public_transport_dictionary` | *(none)* | ✅ |
| Vector POI layers (metro/bikes/parking) | `wfsstore_get` | `id=<layer-uuid>` | ✅ |
| Stop group by name | `dbtimetable_get` | `id=b27f4c17-…` | ⚠️ returns `null` (broken) |
| Stop list w/ coordinates | `dbstore_get` | *(all ids dead)* | ❌ |
| Legacy live trams | `wsstore_get` | `c7238cfe-…` | ❌ |

Full details, fields, and examples: **[`docs/warszawa-api.md`](docs/warszawa-api.md)**.

## ⚠️ Gotchas that will bite you

1. **Errors are HTTP `200`.** Check the body, not the status code:
   - `{"result": null}` → no data · `{"result":"Błędna metoda lub parametry wywołania"}` → bad params
   - `{"result":"false","error":"Błędny apikey lub jego brak"}` → bad key
2. **`busestrams_get` ignores `line`/`brigade`** — it returns *all* vehicles. Filter on `Lines` client-side.
3. **Stale "ghost" vehicles** linger in the feed (timestamps hours/months old). Drop rows whose `Time` is older than ~60–120 s.
4. **No live-ETA endpoint.** Compute predictions by joining **scheduled departures** × **live GPS** on `(line, brigade/brygada)`.
5. **`dbtimetable_get` rows are key/value pair lists**, not objects — fold them into dicts.
6. **Name search is broken** — resolve names via `public_transport_dictionary` → `zespoly_przystankowe`.

## 📍 Stop coordinates — the GTFS join

The API no longer serves per-stop lat/lon (all `dbstore_get` ids are decommissioned). Get
coordinates from the official **WTP GTFS** feed and join on stop id:

```
GTFS stop_id  ==  busstopId (4 digits, zero-padded)  +  busstopNr (2 chars)
   7009 / 01   ⇄   "700901"   →   Marszałkowska, (52.217931, 21.020112)
```

- **Feed:** <https://mkuran.pl/gtfs/warsaw.zip> (official WTP data, rebuilt daily). Use `stops.txt`.
- Only the **6-digit numeric** `stop_id`s are bus/tram posts; `####M` / `####M:E#` are metro.
- Helper: [`scripts/gtfs_stops_join.py`](scripts/gtfs_stops_join.py)

```python
from scripts.gtfs_stops_join import load_stop_index, gtfs_id, split_id
by_id, by_zespol = load_stop_index("stops.txt")   # 6745 posts / 2770 groups
by_id["700901"].lat, by_id["700901"].lon          # 52.217931, 21.020112
gtfs_id("7009", "1")                              # "700901"
```

## ⏱️ Rate limits & polling

UM Warsaw **publishes no rate limit or quota**, and none is enforced at normal volumes
(25 concurrent requests → all `200`, no `429`). There *is* an undocumented load-balancer
abuse filter, so be a good citizen:

| Data | Suggested cadence |
|------|------------------|
| Live GPS (`busestrams_get`) | every **15–20 s** per type (matches server refresh) |
| Timetables (`dbtimetable_get`) | on demand; cache minutes |
| Routes / dictionary / GTFS | once **daily** (cache) |

Use one shared client; retry with backoff on transient errors. Details: [`docs/warszawa-api.md` §12](docs/warszawa-api.md).

## 🌐 Publishing on GitHub

The rendered Redoc docs are pre-built at [`docs/index.html`](docs/index.html). To publish:

1. Push this repo to GitHub.
2. **Settings → Pages → Source:** *Deploy from a branch* → Branch **`main`**, folder **`/docs`**.
3. Your docs go live at <https://tajchert.github.io/warsaw-transport-api/>.

### Regenerating

```bash
npx @redocly/cli lint openapi.yaml                          # validate
npx @redocly/cli build-docs openapi.yaml -o docs/index.html # rebuild rendered docs
```

## 🙏 Credits

Endpoint patterns cross-checked against community projects:
[pywarsaw](https://github.com/BrozenSenpai/pywarsaw),
[warsaw-data-api](https://pypi.org/project/warsaw-data-api/),
[ztm_warszawa](https://github.com/pgrn/ztm_warszawa),
and several reference repos. GTFS feed by [mkuran.pl](https://mkuran.pl/gtfs/).
