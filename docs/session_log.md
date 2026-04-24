---
name: NotizieGeopolitica — Session Log & Experiment Results
description: Registro cronologico di test, decisioni architetturali, esperimenti e risultati notevoli per non ripartire da zero ogni sessione.
type: session-log
last_updated: 2026-04-16
originSessionId: 8b5c0813-7939-4c23-88c2-2afca2ce68f4
---
# NotizieGeopolitica — Session Log

---

## 🗂️ Stato Attuale del Progetto (aggiornato 2026-04-16)

### Pipeline principale
- **Raccolta**: RSS da 12+ fonti (western / eastern / middle_east / russia)
- **Matching**: 2 livelli — keyword overlap (Tier 1) → embedding cosine sim ≥ 0.75 con `all-MiniLM-L6-v2` su Apple MPS (Tier 2)
- **Clustering**: Union-Find algorithm
- **Comparazione**: Gemma 4 e4b via Ollama — analisi multi-prospettiva per cluster
- **Preview**: HTML statico generato da `scripts/generate_preview.py`
- **DB**: SQLite `data/notizie.db` — 4 tabelle principali (sources, articles, story_clusters, comparisons)

### File chiave
```
scripts/generate_preview.py     # genera preview HTML (MODIFICATO: include title dedup)
scripts/cleanup_noise.py        # rimuove cluster rumore dal DB
scripts/ab_base.py              # copia notizie.db → ab_base.db (veloce, per test)
scripts/ab_persona_test.py      # test persona giornalista (A/B/C)
scripts/run_persona_test.sh     # lancia tutti e 3 i test persona
src/analyzer/prompts.py         # tutti i template prompt LLM
src/analyzer/matcher.py         # matching + clustering
src/analyzer/comparator.py      # genera comparisons via LLM
```

### .env configurazione attuale
```
OLLAMA_MODEL=gemma4:e4b
DB_PATH=data/notizie.db
TRANSFORMERS_OFFLINE=1          # aggiunto — evita retry HuggingFace se modello è cached
HF_HUB_OFFLINE=1                # aggiunto — stesso motivo
```

---

## 🧪 Esperimento 1 — AB Test Deduplicazione (Aprile 2026)

**Problema**: La preview mostrava cluster duplicati/frammentati sullo stesso evento (es. Ungheria x3, Iran x4).

**3 approcci testati** con DB isolati (ab_base.db → test_a/b/c.db):

### Versione A — Post-build centroid merge
- **Idea**: dopo il matching, calcola il centroide embedding di ogni cluster, mergia se cosine sim ≥ 0.73
- **Risultato**: "Merge pass: nothing to merge" — i cluster pre-esistenti nel DB copiato hanno centroidi troppo distanti
- **Verdetto**: ❌ Non funziona su cluster pre-esistenti, solo su nuovi formati nella stessa run

### Versione B — Include articoli matched recenti
- **Idea**: durante il matching, include anche articoli con `matched=1 AND fetched_at >= -72h` per allargare i cluster
- **Risultato**: 37 cards (peggiore) — più coppie candidate → cluster ancora più frammentati
- **Verdetto**: ❌ Peggiora la situazione

### Versione C — Preview-level title deduplication ✅ WINNER
- **Idea**: a livello di preview (post-query), calcola embedding dei titoli, mergia cluster con cosine sim ≥ 0.78
- **Implementazione**: Union-Find sui titoli, mantieni il cluster con più articoli per gruppo
- **Iterazioni**:
  - v1: keyword/entity overlap → troppo aggressivo (20 cards, Hungary ancora 3x)
  - v2: `ENTITY_OVERLAP_MIN=1` → troppo aggressivo (5 cards, "Iran" linkava Trump/Pope con blockade)
  - v3: embedding cosine sim su titoli @ 0.78 → **CORRETTA** — trova solo 1 vero duplicato (sim=0.859): "US-Iran talks in Islamabad"
- **Risultato**: 20 comparisons → 19 dopo dedup (1 rimossa)
- **Verdetto**: ✅ Implementato in `generate_preview.py` nella pipeline principale

**Parametro chiave**: `TITLE_DEDUP_THRESHOLD = 0.78` in `generate_preview.py`

**Lezione**: Le variazioni di Hungary (sim 0.555–0.627) e Iran (sim 0.575–0.693) sono storie diverse in punti temporali diversi — non sono duplicati. Solo phrasing quasi identico (sim > 0.78) è un vero duplicato.

---

## 🧹 Esperimento 2 — Cleanup Noise DB (Aprile 2026)

**Problema**: Il DB conteneva cluster irrilevanti (crime domestico, celebrity, sport, politica locale US).

**Soluzione**: `scripts/cleanup_noise.py`
- Rimuove cluster che matchano keyword rumore nel titolo
- Dry-run di default, `--execute` per cancellare davvero
- **Eseguito**: eliminati 14 cluster rumore, reset `matched=0` per 36 articoli orfani

**Keywords rumore** (set definito nel file):
- Celebrity/sport: epstein, kardashian, oscars, grammy, nba finals, super bowl, formula 1, maradona, prince harry
- Crime domestico: molotov cocktail, grand central, serial killer, sexual misconduct
- Politica locale US: swalwell, senate race, governor race, school board, city council, kerala

**⚠️ Attenzione**: keyword "democrat" potrebbe matchare "Democratic Republic of Congo" — da verificare in futuro se si aggiungono fonti africane.

---

## 🎭 Esperimento 3 — Journalist Persona AB Test (Aprile 2026)

**Idea**: Far scrivere le comparisons a Gemma come se fosse allievo di un famoso giornalista americano (senza mai citarlo), per vedere come cambia il framing.

**Implementazione**: `scripts/ab_persona_test.py --persona A/B/C`
- Monkey-patch di `src.analyzer.prompts.compare_perspectives`
- Sostituisce l'header neutro con il persona header prima che il LLM venga chiamato
- DB isolati: `test_persona_{A/B/C}.db`
- Preview: `data/preview_persona_{A/B/C}.html`

### Le 3 Persona

**A — Populist / Anti-Establishment** (scuola Tucker Carlson)
> "chi nell'establishment beneficia di questa narrativa? chi viene messo a tacere?"
- Tono drammatico, morale, anti-consensus
- Framing: i conflitti internazionali sono orchestrati dalle élite a spese della gente comune

**B — Investigative / Civil-Liberties** (scuola Glenn Greenwald)
> "ugualmente scettico verso media liberal occidentali E outlet statali autoritari"
- Identifica le assunzioni condivise da TUTTE le fazioni (le domande che nessuno fa)
- Tono analitico, focus su accountability e trasparenza

**C — Policy-Analytical / Internationalist** (scuola Fareed Zakaria)
> "situa ogni evento nel contesto storico, strutturale e istituzionale"
- Tono formale e accademico
- Focus su balance of power, precedenti storici, ordine internazionale

### Risultati
- **Meccanismo funzionante**: 22 comparisons generate per ogni persona ✅
- **Bug risolto**: ab_base.db aveva già comparisons → persona prompt mai usato. Fix: `DELETE FROM comparisons` prima della run
- **Differenze reali ma sottili**:
  - Vocabolario e tono variano (A: "swept away", "liberated"; B: "institutional failure"; C: "multipolarity")
  - **LIMITE**: struttura sezioni identica (Factual Agreement / Key Differences / Regional Framing) perché hardcodata nel prompt template
- **Miglioramento possibile**: aggiungere istruzioni format-specifiche per ogni persona per differenziazioni più marcate (non implementato — test sufficiente per ora)

**⚠️ Bug fix critico per futuri test persona**: sempre fare `DELETE FROM comparisons` nel DB di test prima di rigenerare, altrimenti il comparator salta le esistenti.

---

## 🔧 Fix e Decisioni Tecniche Notevoli

### HuggingFace network retry noise
- **Problema**: sentence-transformers tentava chiamate HF a ogni load anche con modello cached → log rumorosi, lentezza
- **Fix**: `TRANSFORMERS_OFFLINE=1` + `HF_HUB_OFFLINE=1` in `.env`
- **Come funziona**: `src/config.py` chiama `load_dotenv()` prima che sentence-transformers venga importato

### Python 3.9 compatibility
- `str | None` union type hint non funziona su Python 3.9 (richiede 3.10+)
- Fix: rimuovere type hint nelle funzioni di cleanup_noise.py
- **Mac Mini usa Python 3.9** — tenere a mente per future funzioni

### ab_base.py — perché è veloce
- Originalmente: faceva full collect + summarize (~30+ min)
- Riscritto: `shutil.copy2(notizie.db → ab_base.db)` — 2 secondi
- Motivo: notizie.db ha già tutti gli articoli summarizzati, non serve riprocessare

### Matching threshold
- `SIMILARITY_THRESHOLD = 0.75` in matcher.py
- Tier 1 (keyword): overlap minimo per passare al Tier 2
- Tier 2 (embedding): cosine sim ≥ 0.75 → cluster confermato
- Testato: non abbassare sotto 0.70 (troppi falsi positivi su "Iran" che linka storie diverse)

### Preview: smart dedup + days=3 (implementato 2026-04-16)
- `make preview` usa `--days 3` come default
- Dedup a due soglie:
  - Same-day: cosine sim ≥ 0.78 → keep cluster con più articoli
  - Cross-day: cosine sim ≥ 0.65 → keep cluster più recente (stesso arco narrativo)
- Cap a 15 card massimo (ordinate per data desc)
- Parametri in `generate_preview.py`: `SAME_DAY_THRESHOLD`, `CROSS_DAY_THRESHOLD`, `PREVIEW_MAX_CARDS`
- Traduzione: `TRANSLATE_MODEL=translategemma:latest` in `.env` (superiore a Gemma 4 per traduzioni)

---

## 📋 Backlog / Cose da Fare in Futuro

### Alta priorità
- [ ] **Verifica pipeline notturna**: controllare che il launchd/cron giri regolarmente e che notizie.db cresca correttamente
- [ ] **Traduzione fonti**: al momento solo fonti inglesi. Piano: Gemma 4 traduce titoli/sommari di fonti in cinese/arabo/russo prima del matching

### Media priorità
- [ ] **Cluster merge post-build**: Versione A non ha funzionato su DB copiato ma potrebbe funzionare se integrata nella pipeline live (durante la stessa run di matching)
- [ ] **Persona test v2**: aggiungere format-specific instructions per differenziazioni più marcate tra le 3 voci
- [ ] **Migliorare noise detection**: keyword "democrat" rischio false positive su "Democratic Republic of Congo"

### Bassa priorità / Fase 4
- [ ] Hugo static site + deploy su Cloudflare/GitHub Pages
- [ ] Fonti aggiuntive in lingua nativa (modello embedding multilingue: `paraphrase-multilingual-MiniLM-L12-v2`)
- [ ] Bias meter visuale
- [ ] Feed RSS del sito
- [ ] Trend storici: evoluzione copertura nel tempo

---

## 📊 Metriche DB (snapshot 2026-04-16)

- **Articoli totali**: ~1886 (tutti summarizzati)
- **Cluster attivi** (post-cleanup): ~XX
- **Comparisons generate**: ~22 per run (ultimi 3 giorni)
- **Fonti attive**: 12+ (western: BBC/DW/France24/Reuters, eastern: Xinhua/CGTN/Times of India/NDTV, middle_east: Al Jazeera/TRT, russia: TASS/RT)

---

## 🚀 Come Riprendere in una Nuova Sessione

1. **Leggere questo file** per il contesto aggiornato
2. **Controllare lo stato DB**: `sqlite3 data/notizie.db "SELECT COUNT(*) FROM articles; SELECT COUNT(*) FROM comparisons;"`
3. **Generare preview fresca**: `python scripts/generate_preview.py && open data/preview.html`
4. **Pipeline manuale se serve**: `python -m src.cli collect && python -m src.cli analyze`
5. **Test AB se serve**: `./scripts/run_ab_test.sh` o `./scripts/run_persona_test.sh`
