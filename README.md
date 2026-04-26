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

## License

[MIT](LICENSE)
