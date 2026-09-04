# Parallax

**Same event. Different vantage points.**

Parallax is an automated system that collects geopolitical news from 21 sources across 4 geopolitical blocs (Western, Eastern, Middle East, Russia), identifies when multiple outlets cover the same story, and uses local AI to analyze how each bloc frames the narrative differently.

Updated daily at [bbnss.github.io/parallax](https://bbnss.github.io/parallax/)

## How it works

1. **Collect** — RSS feeds from 21 international outlets
2. **Summarize** — Local AI (Gemma 4) reads and summarizes each article
3. **Match** — Finds the same story across different sources using embeddings
4. **Compare** — AI analyzes where accounts agree, diverge, and what each omits
5. **Translate** — Output in 5 languages (EN, IT, ES, DE, FR)

## Feed & API

Everything the site publishes is plain static JSON — no key, no rate limit.

| URL | What it is |
|---|---|
| [`/feed.json`](https://bbnss.github.io/parallax/feed.json) | [JSON Feed 1.1](https://jsonfeed.org) — **only the stories the latest run added** |
| [`/feed.xml`](https://bbnss.github.io/parallax/feed.xml) | The same, as RSS 2.0, for feed readers |
| [`/archive/manifest.json`](https://bbnss.github.io/parallax/archive/manifest.json) | Months available, story counts, date of the last run |
| `/archive/YYYY-MM.json` | Every story of that month as a rendered, collapsed card |
| `/archive/full/<cluster_id>.json` | One story's full analysis, in all 5 languages |

The feeds carry only what is new, so a reader never sees the same story twice.
Each item adds a `_parallax` object (a JSON Feed extension) with the structured
payload: `cluster_id`, `tier`, `regions`, `article_count`, every source with its
name, region, country and article URL, and `full_analysis_url`.

An archive shard is an array of
`{id, slug, d (date), tier, dupes, html}`, where `html` is the collapsed card in
all five languages. The heavy part — the analysis itself — sits in
`archive/full/<id>.json` as `{"en": "<html>", "it": …}` and is fetched only when
a reader expands that card, which is what keeps both the page and the repository
small.

`dupes` lists the cluster ids that were merged into this story by the
render-time deduplication; the archive is append-only and keyed on cluster id,
so a story is published exactly once.

## Site

The home page shows the last 24 hours. Scrolling loads the archive a month at a
time, and the search box filters titles and "In Breve" summaries in the language
you are reading, going further back on request. Two permalink forms work
anywhere: `#/s/<slug>` opens one story, `#/q/<terms>` reopens a search.

## License

[MIT](LICENSE)
