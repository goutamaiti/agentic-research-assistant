# Frontend design plan

Brief: modern, not generic AI output, only relevant information, unique.

## Concept: the paper's words versus the system's words

The product's value is that every statement can be traced to the paper's own text. The design
makes that distinction the organising rule of the whole interface:

- **Sheet.** Anything quoted from the paper sits on a white "page" with a printed page folio,
  set in a serif face with a highlighter stripe under the words.
- **Desk.** Everything the system says (claims, summaries, controls, chat answers) sits on a
  cool grey "desk" in a sans face, with no boxes around it.

So typeface and surface both tell the reader whose words they are reading. There is no
decorative use of either.

## Palette (named, with roles)

| Name | Light | Dark | Role |
| --- | --- | --- | --- |
| Desk | `#E4E8E6` | `#12161D` | Page background. Cool grey with a faint green cast, like a lab bench |
| Page | `#FFFFFF` | `#1C222C` | Only the paper's quoted text and form inputs |
| Ink | `#1B2230` | `#E6EAF0` | Text. Blue-black, not neutral black |
| Proof blue | `#2438C9` | `#93A0FF` | Links, focus rings, the active tab. The only accent |
| Highlighter | `#FFDE59` | `#FFDE59` at 30 % | The stripe under quoted words. Nothing else uses yellow |
| Verified green | `#17694B` | `#5FD1A0` | Verified status mark and its thread |

Semantic extras, used only for statuses and always with a shape and a word: partial amber
`#8A5300`, flag red `#B3261E` (dark `#FF8A80`).

## Type

- **Instrument Sans** (variable, self-hosted): all interface text, headings, claims, chat
  answers. Role: the system's voice.
- **Source Serif 4** (variable, self-hosted): only text that is the paper's own words
  (quotes, abstract, citations). Role: the paper's voice.
- Scale (px): 13 meta, 15 body, 17 claim and answer text, 22 section heading, 32 paper
  title. Body line length capped at 68 characters. Headings are sentence case, weight 600.

## Layout

Single desk column, 1080 px max, 24 px gutters (16 px at 375). Left edges align to one
line; headings, claims and controls share it. Sheets are the only surfaces with a border.

```
Upload (#/)
+--------------------------------------------------------------+
| Agentic Research Assistant                                   |
+--------------------------------------------------------------+
| Analyse a paper                  | Your papers               |
| One PDF, up to 30 MB. ...        | Title of paper A          |
| +--------------------+           |  3 pages  (v) Analysed    |
| | sheet: drop a PDF  |           |  Open analysis  Check ... |
| | or choose a file   |           | Title of paper B          |
| +--------------------+           |  1 Upload validation  (v) |
| [Upload and analyse]             |  2 Document extraction .. |
|                                  |                           |
| (v) Backend: all components OK   |                           |
+--------------------------------------------------------------+

Analysis (#/analysis/<id>)
+--------------------------------------------------------------+
| <- All papers   Paper title                                  |
| Analysis | Evidence | Assistant                              |
+---------------+----------------------------------------------+
| Contents      | Paper title (32)                             |
|  Abstract (v) | Authors, year, venue, DOI                    |
|  Problem  (v) | [Download PDF report] [Download JSON report] |
|  ...  (sticky)| 23 of 27 claims verified  [====== = - ]      |
|               |                                              |
|               | Research problem            (v) Extracted    |
|               | (v) Claim text in sans                       |
|               | |   Show quote, p. 101                       |
|               | |   +--------------------------+ p.101     |
|               | |   | serif quote, highlighted |           |
|               | |   +--------------------------+           |
+---------------+----------------------------------------------+

Evidence (#/evidence/<id>)
+--------------------------------------------------------------+
| 23 of 27 claims verified against the paper's text            |
| [All 27] [(v) Verified 23] [(o) Partly 2] [(x) Unsupported 1]|
+---------------------------+----------------------------------+
| (v) Claim text            | +------------------------------+ |
|     Verified, author claim|-| serif quote           p. 101 | |
|     Why it was marked so  | +------------------------------+ |
+---------------------------+----------------------------------+

Assistant (#/assistant/<id>)
+--------------------------------------------------------------+
| Ask this paper     (reading column, 720 px)                  |
| You: What recall did the retriever reach?                    |
| Answer in sans prose                                         |
|   [p. 101  Results v]  -> sheet with the cited passage       |
| (! ) Not enough evidence in the paper     (when applicable)  |
| Background, not from the paper: ...       (dashed, separate) |
| [ Ask a question about this paper ......... ] [Ask]          |
+--------------------------------------------------------------+
```

## Alignment and principles

1. Whose words? Serif on white means "the paper said this". Sans on grey means "the system
   said this". Never mix them in one block.
2. Structure is information. Borders belong to sheets only. A vertical or horizontal
   "thread" in the status colour joins a claim to its quote; it is dashed when no quote
   was located. Numbers appear only on the six pipeline stages, which are a real sequence.
3. Status is a shape plus a word, never colour alone: filled check (verified), half disc
   (partial), outlined cross (unsupported), triangle (contradicted), dashed ring (not
   verifiable), clock (pending).
4. No cards. Sections are separated by space and one heading, not boxes.
5. Motion: the verification bar fills once on the analysis page (the one orchestrated
   moment); quotes expand in response to a click. All disabled under reduced motion.
6. Copy says what happens ("Download PDF report"), errors say what failed and what to do.

## Self-review and revisions

First draft read as: sidebar contents list + stacked section cards + pill badges for status +
serif section headings. Against the brief that is the stock "documentation site" kit. Changes:

- **Serif headings dropped.** A serif display face reads as a default for "academic". Serif is
  now reserved for the paper's own words, which gives it a job.
- **Cards removed.** Section cards became open typographic blocks; only quote sheets have a
  surface.
- **Pill badges replaced** by a shaped mark plus plain text, which also carries the thread
  colour. This is where status, claim and quote get connected.
- **Contents rail now carries information.** Each entry shows the weakest verification
  status inside that section, so a reader can see where to look first, instead of being a
  bare link list.
- **Health card removed from the main flow.** It is a collapsed one-line footer unless the
  backend is unreachable, when it becomes the first thing on the page.
- **Evidence page split view.** Claim left, quote right, joined by a horizontal thread,
  rather than a list of stacked blocks.
- **Palette check.** No cream, no terracotta, no near-black plus acid accent. Yellow is
  limited to the highlighter stripe so it keeps its meaning.

### Second pass, after seeing the built pages in a browser

- **Margin marks were noise.** A column of identical green discs on the Analysis page said
  nothing. Verified claims now get a small dot; only flagged claims (partial, unsupported,
  contradicted, not verifiable) get a full-size shape, so exceptions stand out.
- **Thread alignment.** The horizontal thread now meets the first line of the claim and
  enters the sheet at that height. On narrow screens the same thread runs vertically down
  the left edge and stubs into the sheet.
- **Assistant column** was centred while every other page is left-aligned; it now shares the
  left edge. Assistant replies are labelled "Answer" (not "From the paper") because they can
  also carry a separate general explanation.
- **Duplicate paper title** on the Analysis page (bar and heading) removed from the bar.
- **Mobile:** metadata stays two-column, drop area shortens, no horizontal scroll at 375 px.

## The one bold element

The **claim-to-quote thread**: each claim is joined by a line, coloured and shaped by its
verification status, to a white serif "sheet" holding the verbatim quote with a highlighter
stripe and the printed page folio. Everything else is deliberately quiet.
