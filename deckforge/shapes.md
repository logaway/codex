# Page shapes

A shape declares the structure of the information on a page. Pick the shape
that matches what the content actually is — not the one that looks nicest.
Forcing a timeline into `compare` is a mismatch the reader feels immediately.

`deck.json` structure:

```json
{
  "meta": {"contract": "editorial-report", "footer": "Internal · Do not distribute"},
  "pages": [ { "shape": "...", ... } ]
}
```

## Write action titles, not labels

The highest-leverage content rule in this skill, and the one most often
skipped. A page title should state the page's conclusion as a full sentence —
"Margins expanded as freight costs fell" — not name its topic — "Margins".

The payoff is that a reader can follow the whole argument from the titles
alone, which is most of what separates a deck that reads as professional from
one that reads as a pile of slides. It costs nothing visually.

| Label title | Action title |
|---|---|
| 四個階段 | 分四階段切換，每階段都可回滾 |
| 風險 | 三個風險需要在本週決策 |
| Q3 Results | Q3 beat plan on volume, missed on margin |

`build.py` warns when a title looks like a bare label. Treat the warning as
a prompt to rewrite the title, not as noise. Exception: `title` and
`statement` pages, which work differently and are not audited.

---

All shapes accept optional `eyebrow` (a short kicker, 2–6 chars in CJK) and
`title`. Text length limits are enforced by the builder — it warns and
truncates rather than overflowing, so treat a warning as "cut this copy".

---

## title
Opening page. One per deck, first.
```json
{"shape": "title", "eyebrow": "Annual review",
 "title": "Growth holds, structure strains",
 "subtitle": "One line of framing, optional"}
```
Keep `title` under ~14 CJK chars or ~40 Latin. A title that wraps to three
lines has stopped being a title.

## metrics
2–4 numbers as the argument. The strongest shape for looking authoritative,
because large figures create hierarchy for free.
```json
{"shape": "metrics", "title": "...",
 "items": [{"label": "Retention", "value": "42%", "unit": "repeat rate",
            "note": "One or two sentences of context."}]}
```
`value` should be short — "42%", "3.1pt", "¥2.4M". A sentence in `value`
defeats the shape.

## points
2–4 parallel ideas of equal weight. Use when items are genuinely parallel; if
one matters more, use `statement` for it instead and drop the rest.
```json
{"shape": "points", "title": "...",
 "items": [{"heading": "Short heading", "body": "Two or three sentences."}]}
```

## compare
Exactly two sides. Use for real oppositions — before/after, ours/theirs,
durable/one-off. Do not use it for two topics that merely coexist.
```json
{"shape": "compare", "title": "...",
 "sides": [{"label": "Durable", "heading": "Structural gains",
            "rows": ["One line per row", "Up to five rows"]}]}
```

## timeline
2–5 ordered stages. Order must carry meaning the reader needs — that is the
whole justification for numbering. A list that happens to have five items is
not a timeline.
```json
{"shape": "timeline", "title": "...",
 "steps": [{"when": "Q1", "heading": "Stage name", "body": "What happens."}]}
```

## statement
One claim, large, surrounded by space. The deck's turning point.
```json
{"shape": "statement", "eyebrow": "Conclusion",
 "text": "The single sentence the audience should leave with.",
 "attribution": "Optional line beneath"}
```
Use once or twice per deck. Its force comes from scarcity — a deck of
statements is a deck of shouting.

## table
A comparison or assessment grid. The most common business exhibit, and the
fastest way to make a page look like a document rather than a slide.
```json
{"shape": "table", "title": "...",
 "columns": ["Capability", "Us", "Field", "Gap"],
 "weights": [3, 1, 1, 1],
 "rows": [["Onboarding", "Strong", "Mixed", "Ahead"]]}
```
`weights` sets relative column widths; the first column is set in `h3` as the
row label. Up to 8 rows — beyond that it stops being readable at a distance.

## pipeline
Ordered stages with a current position. Use when the audience needs to know
where a programme stands, not just what the phases are.
```json
{"shape": "pipeline", "title": "...",
 "stages": [{"label": "Diagnose", "state": "done", "note": "One or two lines."},
            {"label": "Design", "state": "current"},
            {"label": "Pilot", "state": "next"}]}
```
`state` is `done`, `current`, or `next`. Only `current` gets the accent fill —
that is the whole point of the exhibit, so do not mark two stages current.

---

## Page chrome

Set `meta.org` and `meta.date` and every page gets a top rail: an organisation
mark left, a date or status right, a hairline beneath. A page can override the
right side with its own `stamp` ("DRAFT 03", "CONFIDENTIAL").

This is worth doing. Reference decks almost all carry a rail, and it does
something no amount of palette work can: it tells the reader what kind of
document they are looking at before they read a word.

---

## Sequencing

Vary the shapes. Five consecutive `points` pages is the structural equivalent
of a monotone: each page is fine and the deck is dull. A common working
rhythm is `title → points → metrics → compare → statement`.

Keep pages at a similar fullness. The checker flags large ink-density swings
because a deck that alternates crammed and empty reads as unplanned, even when
every page passes on its own.
