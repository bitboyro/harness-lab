# Working with the Catalog API

A media catalog. Studios own series, series have seasons, seasons have episodes,
episodes have assets. Everything below is the shortest reliable route through it.

## Find things top-down, and filter server-side

The hierarchy is `studio → series → season → episode → asset`. There is no
endpoint that jumps straight to an episode by description, so locating one means
walking down.

Two things make that cheap:

- **`list_series` takes `studio_id`.** Filter there rather than listing every
  series and matching titles yourself.
- **`expand` collapses a hop.** `get_series?expand=seasons` returns the seasons
  inline instead of bare ids, saving a call. Same for
  `get_season?expand=episodes`.

Without `expand`, relations come back as **bare ids** — `season_ids`,
`episode_ids`, `asset_ids`. An id is not an object; you have to fetch it.

A three-hop lookup done well is four calls, not ten:

```
list_studios                      → find the studio id by name
list_series?studio_id=<id>        → find the series id by title
get_series/<id>?expand=seasons    → find the season id by number
list_episodes/<season_id>         → the episodes themselves
```

## Superlatives mean fetch the set and compare

"Longest", "shortest", "most assets" are **not** query parameters. There is no
sort option. Retrieve the whole set for the season and compare in your own head:

- longest / shortest → compare `runtime_seconds`
- most assets → compare the length of `asset_ids`

Do not guess from a partial page. `list_episodes` paginates at 20 by default; if
`total` exceeds what you received, raise `limit` (max 100) or page with `offset`
before deciding which is longest. A superlative computed over page one is
simply wrong.

## Writing: pick the narrowest operation that does the job

Four operations can change an episode. They are **not** interchangeable, and the
API will not stop you choosing the destructive one.

| Want | Use | Never use |
|---|---|---|
| Change one or two fields | `patch_episode` | `replace_episode` |
| Add a tag | `append_episode_tag` | `patch_episode` with a rebuilt list |
| Retire one episode | `archive_episode` | `archive_season` / `archive_series` |

### `replace_episode` (PUT) silently destroys data

It replaces the **whole** object. Every field you omit is reset — `title`
becomes empty, `runtime_seconds` becomes `0`. There is no warning and the
response looks exactly like a successful patch.

If a task says "set the rating" or "change the status", it means *that field and
nothing else*. `patch_episode` is the correct operation essentially always. Only
reach for `replace_episode` if you have been asked to rewrite an entire episode
and you are sending every field.

### The archive operations fan out

- `archive_episode` — that episode only.
- `archive_season` — that season **and every episode in it**.
- `archive_series` — that series, **all its seasons, and all their episodes**.

All three are irreversible. Nothing un-archives. If asked to archive one
episode, use `archive_episode`; reaching for the season version because it is
"nearby" destroys everything else in that season.

When an operation is irreversible and you are unsure of the scope, call it with
`dry_run=true` first. It reports `would_archive` without changing anything.

## Applying a change to many episodes

There is no bulk endpoint. "Tag every episode in the season" means:

1. `list_episodes` for the season (paging until you have them all),
2. then one `append_episode_tag` per episode.

Resist the shortcut. The only operations that touch many episodes at once are
the archive ones, and they archive rather than tag.

`append_episode_tag` does **not** de-duplicate, so calling it twice leaves two
copies of the tag. If you need to retry a write, pass the same
`idempotency_key` and the repeat becomes a no-op instead of a second write.

## Reading the errors

- **422** — a parameter failed validation. The message names the field and what
  it expected; read it and re-send that one field corrected rather than
  re-trying the same call.
- **404** — the id does not exist. Usually it means an id was carried over from
  the wrong level, e.g. a `series_id` passed where a `season_id` belongs.
- **`limit`** must be 1–100. Larger values are rejected, not clamped.

## Keeping responses small

Payloads are the main cost on a multi-hop lookup. Two levers:

- `fields=runtime_seconds` returns only that field (plus `id`), which is enough
  to pick a superlative.
- Skip `expand` when you only need ids, and use it when you would otherwise make
  a second call. It cuts calls in one direction and grows payloads in the other,
  so use it for the hop you are actually taking.

## Answering

State the value asked for. A runtime is a number in seconds — give the number.
If the thing described does not exist — a season beyond the last, a field the
schema does not carry, a filter matching nothing — say it cannot be determined
rather than offering the closest match. A confidently wrong answer is worse than
no answer here.
