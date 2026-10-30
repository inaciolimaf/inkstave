# 106 — Visual identity: the manuscript on the desk

This extends the landing's identity ("ink on paper", `frontend/src/modules/landing/landing.css`) to the signed-in app, which still looks like
the shadcn default: `Card` in 15 files, 9 Tailwind text sizes plus more than 10 arbitrary ones, a dark
theme that is the light one inverted.

## 1. The concept

A project is a manuscript on a writer's desk. The user drafts, marks up and revises a text, which is
what they do in Inkstave. It changes the layout of three screens:

- **Projects**: an index of works, ruled lines with title and date, not a table inside a card.
- **Editor**: the sheet in the middle, the file tree as the contents, the preview as the proof beside it.
- **Diff review**: a reviewer's marks in the margin of the text, not a generic dialog of cards.

## 2. The skeleton

`Manuscript` is the root of every screen except the landing and the editor workspace, which has
`Desk`. Primitives: `Manuscript`, `ManuscriptHeader`, `Rule`, `Margin`, `ManuscriptFoot`.

- Secondary information goes in the margin or the foot, not in another box.
- The header says what the thing is. No grey subtitle explaining the screen.
- `Card` survives only on floating surfaces (dialog, popover). No card inside a card.
- Two layers: **the printed layer** (type, rules, numbering) and **the hand** (what a person did:
  edits, comments, cursors, the agent's proposals). "Who put this here?" tests any element.

## 3. Meanings

| Colour or mark | Means | Never used for |
|---|---|---|
| ink (navy) | the text, and the one main action | decoration |
| paper | the surface being worked on | status |
| reviewer's red | an error that needs action now; a line marked for removal in a review | a past mistake in a list |
| green | an added line, something saved or applied | brand |
| amber | a warning from the compiler, a connection in doubt | emphasis |
| collaborator colours | one person's cursor | anything else; content colours in `src/lib/palettes.ts` |

Budgets: one solid action per screen. Red appears only for what needs action, and a pending review is an action. Colour is never alone: a
`+`, an icon or a word says the same thing. Metadata is plain text, not a badge.

## 4. Type

Newsreader for titles, JetBrains Mono for LaTeX, Source Sans 3 for the interface: the user chose it on
the pilot over Inter and IBM Plex Sans. The landing keeps Inter. Sizes are the tokens `small`, `body`, `heading`, `title`,
`figure`. Tabular figures on dates and counts.

## 5. Themes

Light is warm paper under daylight. Dark is carbon paper at night: a warm near-black with chalk-like
ink, its own decisions rather than an inversion.

## 6. Motion

Almost none: this is a tool used for hours. The material is ink settling: opacity and a small
`transform`, at most `--motion-base`. No entrance animation on screens. Only loading loops. The
landing is the one exception, by the user's decision: it is a marketing page rather than a tool, so its
rich motion and the loops of `float-soft`, `pulse-dot`, `cursor-bob` and the agent demo stay, and all of
them stop under reduced motion.

## 7. Screens

| Screen | What it is in the concept | What changes in the layout |
|---|---|---|
| Projects | index of works | ruled list, no table header or card, actions in the margin |
| Editor | the desk | panels lose their boxes, one bar, the sheet in the middle |
| Diff review | reviewer's marks | hunks in the text's flow, decisions in the margin |
| Settings | front matter | one ruled column |
| Sign-in, register, e-mail flows | title page | one centred sheet, no card on grey |
| Error, 404 | an errata slip | designed screen in the product's voice |

## 8. Pilot and order

Pilot: **Projects**, the entry to every session and the screen where the skeleton shows best. Nothing
else moves until the user judges it in both themes, at 390 px and on desktop. Then: sign-in, settings,
editor, diff review, one commit each.

## 9. Guarantees

| Rule | Guarantee |
|---|---|
| One root per screen | `expectOneManuscript()` in each whole-screen test; `Card` restricted by lint |
| Colour by token | `no-restricted-syntax` over raw palette classes |
| Contrast | `frontend/tests/contrast.test.ts` |
| Motion | `frontend/tests/keyframes.test.ts` |
| No `100vh` | `frontend/tests/css-rules.test.ts` |
| Budget | `make web-budget` |
| Accessibility | `frontend/e2e/a11y.spec.ts`, both themes |
