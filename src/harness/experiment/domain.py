"""The fictional media catalog: studio -> series -> season -> episode -> asset.

Two requirements pull against each other and both must hold.

**Contamination-free.** Nothing here may exist in pretraining, or Z0 scores
above zero and every result is void. So names are generated from invented
morphemes rather than drawn from any real catalogue.

**Coherent, not gibberish.** Random tokens would introduce performance noise
unrelated to packaging — a model struggling to keep `xq7v` apart from `xq7b` is
not telling us anything about MCP versus curl. So generated names are
pronounceable, look like real titles, and stay stable under a seed.

Answers must also be *unguessable*: runtimes, ratings and ids are drawn from the
seeded world, never inferable from the question. A task whose answer can be
reasoned out without calling the API measures reasoning, not tool use.

Contract: archive/reference/experiment-design.md#the-test-api, #grading
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

# Invented morphemes. Pronounceable in English, and none is a real word or a
# real studio, series, or place name.
_ONSET = ("bral", "cend", "dorv", "fask", "gith", "hald", "jorn", "kelv",
          "lund", "morv", "nask", "orth", "pelm", "quor", "risk", "sarn",
          "thal", "veld", "wrenn", "yast", "zorm", "askr", "brind", "corv")
_CODA = ("ara", "eth", "ora", "ise", "una", "elle", "iri", "ovo", "yra",
         "ane", "ilo", "ura", "esse", "ondo", "ika", "arn")
_QUALIFIER = ("Ascendant", "Hollow", "Latent", "Umbral", "Verdant", "Ninth",
              "Sunken", "Cardinal", "Perennial", "Fractured", "Quiet", "Vast")
_NOUN = ("Meridian", "Arcade", "Cadence", "Lantern", "Threshold", "Reverie",
         "Aperture", "Bastion", "Vantage", "Interval", "Quarry", "Tessera")

_GENRES = ("procedural", "anthology", "docufiction", "serial-drama",
           "speculative", "period-piece", "microseries")
_STATUSES = ("draft", "scheduled", "released", "embargoed")
_RATINGS = ("G", "PG", "PG-13", "TV-14", "TV-MA", "unrated")
_ASSET_KINDS = ("master", "proxy", "subtitle", "trailer", "still", "audio-stem")


def _word(rng: random.Random) -> str:
    return rng.choice(_ONSET) + rng.choice(_CODA)


def _studio_name(rng: random.Random) -> str:
    return f"{_word(rng).capitalize()} {rng.choice(('Pictures', 'Studios', 'Works', 'Collective', 'House'))}"


def _title(rng: random.Random) -> str:
    if rng.random() < 0.45:
        return f"The {rng.choice(_QUALIFIER)} {rng.choice(_NOUN)}"
    return f"{_word(rng).capitalize()} {rng.choice(_NOUN)}"


def _id(rng: random.Random, prefix: str) -> str:
    """Opaque, so an id can never be guessed from the entity it names."""
    return f"{prefix}_{rng.getrandbits(28):07x}"


@dataclass
class Asset:
    id: str
    episode_id: str
    kind: str
    bitrate_kbps: int
    checksum: str


@dataclass
class Episode:
    id: str
    season_id: str
    number: int
    title: str
    runtime_seconds: int
    rating: str
    status: str
    #: Bare ids, not embedded objects — fetching them is a second call unless
    #: the caller uses ?expand=. This is API-3, and it is what makes hop depth
    #: a real cost rather than a label.
    asset_ids: list[str] = field(default_factory=list)
    archived: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class Season:
    id: str
    series_id: str
    number: int
    episode_ids: list[str] = field(default_factory=list)
    archived: bool = False


@dataclass
class Series:
    id: str
    studio_id: str
    title: str
    genre: str
    season_ids: list[str] = field(default_factory=list)
    archived: bool = False


@dataclass
class Studio:
    id: str
    name: str
    founded: int
    series_ids: list[str] = field(default_factory=list)


@dataclass
class World:
    """One seeded catalogue. The source of truth for both the API and the keys."""

    seed: int
    studios: dict[str, Studio] = field(default_factory=dict)
    series: dict[str, Series] = field(default_factory=dict)
    seasons: dict[str, Season] = field(default_factory=dict)
    episodes: dict[str, Episode] = field(default_factory=dict)
    assets: dict[str, Asset] = field(default_factory=dict)

    # ---- navigation helpers used by both the API and the task generator ----

    def episodes_of(self, season_id: str) -> list[Episode]:
        season = self.seasons[season_id]
        return [self.episodes[e] for e in season.episode_ids]

    def seasons_of(self, series_id: str) -> list[Season]:
        return [self.seasons[s] for s in self.series[series_id].season_ids]

    def series_of(self, studio_id: str) -> list[Series]:
        return [self.series[s] for s in self.studios[studio_id].series_ids]

    def snapshot(self) -> dict[str, Any]:
        """Deep state for diff-based grading of writes."""
        from dataclasses import asdict
        return {
            "studios": {k: asdict(v) for k, v in self.studios.items()},
            "series": {k: asdict(v) for k, v in self.series.items()},
            "seasons": {k: asdict(v) for k, v in self.seasons.items()},
            "episodes": {k: asdict(v) for k, v in self.episodes.items()},
            "assets": {k: asdict(v) for k, v in self.assets.items()},
        }


@dataclass(frozen=True, slots=True)
class WorldShape:
    """Knobs the difficulty sweep turns.

    ``fan_out`` is the one that matters most: it sets how many episodes a
    season-wide operation touches, which is what separates a cheap mistake from
    an expensive one on RW-fan tasks.
    """

    studios: int = 4
    series_per_studio: int = 3
    seasons_per_series: int = 3
    episodes_per_season: int = 12
    assets_per_episode: int = 3


def shape_for_cores(cores: int, base: WorldShape = WorldShape()) -> WorldShape:
    """Grow a world until it holds at least ``cores`` seasons.

    One core needs one season. Studios are widened rather than seasons deepened,
    so season numbers stay realistic (a series with 40 seasons would be a
    conspicuous artifact) and fan-out stays whatever the sweep set it to.
    """
    from dataclasses import replace

    per_studio = base.series_per_studio * base.seasons_per_series
    if per_studio < 1:
        raise ValueError("series_per_studio and seasons_per_series must be >= 1")
    studios = max(base.studios, -(-cores // per_studio))  # ceiling division
    return replace(base, studios=studios)


def build_world(seed: int, shape: WorldShape = WorldShape()) -> World:
    """Generate a catalogue. Same seed, same world, every time.

    Determinism is not a convenience here — it is what lets an instance-per-run
    rig re-create byte-identical state for every repeat, so variance measures
    the model rather than the fixture.
    """
    rng = random.Random(seed)
    world = World(seed=seed)
    used_titles: set[str] = set()

    def unique_title() -> str:
        for _ in range(100):
            candidate = _title(rng)
            if candidate not in used_titles:
                used_titles.add(candidate)
                return candidate
        # Deterministic fallback; collisions are near-impossible at these sizes.
        candidate = f"{_title(rng)} {len(used_titles)}"
        used_titles.add(candidate)
        return candidate

    for _ in range(shape.studios):
        studio = Studio(id=_id(rng, "st"), name=_studio_name(rng),
                        founded=rng.randint(1948, 2019))
        world.studios[studio.id] = studio

        for _ in range(shape.series_per_studio):
            series = Series(id=_id(rng, "sr"), studio_id=studio.id,
                            title=unique_title(), genre=rng.choice(_GENRES))
            world.series[series.id] = series
            studio.series_ids.append(series.id)

            for season_number in range(1, shape.seasons_per_series + 1):
                season = Season(id=_id(rng, "sn"), series_id=series.id,
                                number=season_number)
                world.seasons[season.id] = season
                series.season_ids.append(season.id)

                for episode_number in range(1, shape.episodes_per_season + 1):
                    episode = Episode(
                        id=_id(rng, "ep"),
                        season_id=season.id,
                        number=episode_number,
                        title=unique_title(),
                        # Unguessable: a wide range with second-level precision,
                        # so no plausible default can be reasoned out.
                        runtime_seconds=rng.randint(1_100, 4_300),
                        rating=rng.choice(_RATINGS),
                        status=rng.choice(_STATUSES),
                        tags=[_word(rng) for _ in range(rng.randint(0, 3))],
                    )
                    world.episodes[episode.id] = episode
                    season.episode_ids.append(episode.id)

                    for _ in range(shape.assets_per_episode):
                        asset = Asset(
                            id=_id(rng, "as"),
                            episode_id=episode.id,
                            kind=rng.choice(_ASSET_KINDS),
                            bitrate_kbps=rng.choice((800, 1_500, 4_000, 12_000)),
                            checksum=f"{rng.getrandbits(48):012x}",
                        )
                        world.assets[asset.id] = asset
                        episode.asset_ids.append(asset.id)

    return world
