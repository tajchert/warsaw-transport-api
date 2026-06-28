#!/usr/bin/env python3
"""
Join WTP GTFS stops.txt <-> api.um.warszawa.pl busstopId/busstopNr, giving the
per-stop coordinates the live API no longer serves (see docs/warszawa-api.md §7b).

KEY RULE (verified live 2026-06-28 against the official feed):
    GTFS stop_id  ==  busstopId (4 digits, zero-padded) + busstopNr (2 chars)
    e.g.  busstopId=7009, busstopNr=01  <->  stop_id "700901"  (Marszałkowska)

Only the 6-char numeric stop_ids (location_type=0) are bus/tram/SKM stop *posts*
addressable this way. The feed also contains:
    - 4-char numeric ids   -> rail station nodes (e.g. "1901" Warszawa Zoo), no post
    - 5-char "....M" ids    -> metro station parents (location_type=1)
    - 8/9-char "....M:E#/:P#" -> metro entrances/platforms (location_type=2)
These are NOT addressed by the bus/tram busstopId/busstopNr pair and are skipped
by load_stop_index() unless include_non_post=True.

GTFS feed: https://mkuran.pl/gtfs/warsaw.zip  (official WTP data, daily). Use stops.txt.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass


@dataclass(frozen=True)
class Stop:
    stop_id: str        # GTFS, e.g. "700901"
    busstop_id: str     # zespół, 4 digits, e.g. "7009"
    busstop_nr: str     # słupek/post, 2 chars, e.g. "01"
    name: str
    lat: float
    lon: float
    street: str
    town: str


def gtfs_id(busstop_id: str | int, busstop_nr: str | int) -> str:
    """API (busstopId, busstopNr) -> GTFS stop_id. '7009','1' -> '700901'."""
    return f"{int(busstop_id):04d}{int(str(busstop_nr)):02d}"


def split_id(stop_id: str) -> tuple[str, str]:
    """GTFS stop_id -> (busstopId, busstopNr). '700901' -> ('7009','01')."""
    if not (len(stop_id) == 6 and stop_id.isdigit()):
        raise ValueError(f"{stop_id!r} is not a 6-digit bus/tram stop post id")
    return stop_id[:4], stop_id[4:6]


def load_stop_index(stops_txt_path: str, include_non_post: bool = False):
    """Parse stops.txt -> (by_gtfs_id, by_zespol) dicts of Stop.

    by_gtfs_id:  "700901" -> Stop
    by_zespol:   "7009"   -> [Stop, ...]   (all posts in the group)
    """
    by_gtfs_id: dict[str, Stop] = {}
    by_zespol: dict[str, list[Stop]] = {}
    with open(stops_txt_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = row["stop_id"]
            is_post = len(sid) == 6 and sid.isdigit()
            if not is_post and not include_non_post:
                continue
            bid, nr = (sid[:4], sid[4:6]) if is_post else (sid, row.get("stop_code", ""))
            s = Stop(
                stop_id=sid, busstop_id=bid, busstop_nr=nr,
                name=row["stop_name"],
                lat=float(row["stop_lat"]), lon=float(row["stop_lon"]),
                street=row.get("street_name", ""), town=row.get("town_name", ""),
            )
            by_gtfs_id[sid] = s
            by_zespol.setdefault(bid, []).append(s)
    return by_gtfs_id, by_zespol


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "stops.txt"
    by_id, by_zespol = load_stop_index(path)
    print(f"loaded {len(by_id)} stop posts in {len(by_zespol)} stop groups")
    demo = by_id.get("700901")
    if demo:
        print("700901 ->", demo)
    print("gtfs_id('7009','1') =", gtfs_id("7009", "1"))
    print("split_id('700901')  =", split_id("700901"))
