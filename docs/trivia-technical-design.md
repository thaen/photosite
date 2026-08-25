# Phone Trivia: technical design

## Status

This document specifies the application before implementation. It authorizes a development-host
prototype and automated tests, but not S3 publication. The names, state transitions, and test
cases below are the contract for that work.

## Product boundary

The product is a pass-the-phone trivia game for people sitting together. It uses the familiar
six-category, collect-one-marker-per-category, then answer-a-final-question structure. It has no
board, movement, die, countdown timer, accounts, server, network play, API calls, desktop layout,
or copied visual identity. The visible product name is **Trivia**.

Trivial Pursuit is a Hasbro trademark. The implementation may use the game structure described by
this document, but it must not use the trademark, logo, board layout, card layout, tokens, or
other Hasbro visual material. Hasbro's published rules describe six category markers followed by a
final correct answer as the win condition.

## People and roles

The phone changes hands every turn.

- **Active player.** The person whose turn it is. This person answers aloud and does not touch the
  phone during the turn.
- **Reader.** The next person in the randomized turn order. The reader holds the phone, chooses
  the category that the active player selects aloud, reads the question and visible answer, and
  judges the response.
- **Group.** The people playing. The group chooses the category for a final question.

The first release has individual players only. It does not have teams, remote players, user
accounts, or a separate host role.

## Setup screen

The first screen is titled **Who’s playing?** It contains no scrolling content.

### Player selection

The default selectable people are all selected:

1. Nora
2. Claire
3. Cori
4. Ethan

Each name is a large toggle button. Tapping a selected name unselects it, and tapping an
unselected name selects it. The screen shows no hidden roster, custom-name field, or automatic
player substitution in the first release.

Each selected person has a Difficulty section with large Easy, Medium, and Hard toggle buttons.
The selected difficulties are part of that player's setup, not a property of the whole game.
Nora, Cori, and Ethan start with Easy, Medium, and Hard selected. Claire starts with Easy and
Medium selected. A person cannot start without at least one selected difficulty; the setup screen
names that person in a blocking error. Unselected people have no active difficulty controls.

At least two people must be selected. Pressing Start Game with fewer than two selected people
shows a blocking, plain-language error on the setup screen: `Select at least two players.` The app
does not silently reselect a person.

### Question set

The first release uses one locally bundled Trivia API review bank. It has the strongest current
combination of broad source categories, source difficulty labels, and local cached data. The setup
screen has no question-bank selection control. The first release has no Family or Adult label, no
age filter, and no age-appropriateness field.

### Start Game

Start Game creates a new game, uses the bundled bank and the selected people with their selected
difficulties, performs a Fisher–Yates shuffle of the selected player identifiers, saves the game
state, and enters the first category-choice screen. The shuffle order is the turn order for the
whole game.

Starting a new game replaces a saved unfinished game. The setup screen must ask for confirmation
when an unfinished game exists, because replacement loses the saved score and used-question list.

## Category model

Each playable bank declares exactly six category slots. Every slot is a source-provided category,
not a category invented by the application or inferred by a model. Its display label is the source
label, with only reversible presentation normalization such as replacing underscores with spaces
and title-casing. The slot also has one app color token.

A source with more than six categories may supply a bank only after curation selects six of its
existing categories. For example, The Trivia API has ten source categories. A first playable bank
may select six of those exact categories, but it may not merge or relabel them with an LLM. A
source with fewer than six usable categories cannot supply this game structure.

The bank's category registry defines the label and color shown in the app. Each question has
exactly one declared source category. The score display has one colored wedge per declared slot.

## Turn flow

The app uses a finite state machine. A fresh page reload restores the saved state and redraws the
same state; it does not reroll the order or choose a new question.

### 1. Category choice

The page identifies the active player and reader in text such as `Alice’s turn — hand the phone to
Bob.` It displays six large category buttons, each with its category color and full text label.
Bob reads the choices. Alice chooses aloud. Bob taps the chosen category.

Before displaying a question, the app selects one unused question in the bundled bank and category
whose source difficulty is selected for the active player. Question selection is random within that
eligible set. It records the selected question identifier in the saved state before rendering it,
so a refresh cannot draw a different question. A selected category with no eligible question is a
blocking data error that names the player, category, and selected difficulty set.

### 2. Question and judging

The question screen has these items in this order, all visible without scrolling:

1. Active-player and reader names.
2. Category color and category name.
3. Full question text.
4. Every source answer choice, when the source provides choices.
5. Full correct answer text.
6. A Hide Answer button.
7. A source difficulty label only when the question has a difficulty value.
8. Correct, Incorrect, and Skip Question buttons.

Bob reads the question and any choices to Alice, hears the answer, consults the visible correct
answer, and presses Correct or Incorrect. The application does not attempt automatic answer
matching.

Hide Answer conceals the full answer and changes its own label to Show Answer. It does not conceal
the question, answer choices, category, difficulty, or judgement buttons. Show Answer restores the
full answer. This visibility state is saved before redraw, so a refresh preserves it while the
phone is with the active player.

Correct fills the active player's wedge for the selected category if it is empty. A correct answer
in a category already filled does not create a second wedge. Incorrect leaves the score unchanged.
Both actions lead to the score summary.

### 3. Score summary and handoff

The summary page shows every player’s six-wedge pie. Filled wedges use their category color; empty
wedges retain the category outline. It also states the result of the completed turn and points to
the next active player with a large arrow and text such as `Pass the phone to Charlie.`

One large Next Turn button advances the turn index modulo the shuffled turn order and returns to
Category choice. The reader is always the player after the active player in that order. With two
players, the reader is the other player.

### 4. Final question

When a player has all six wedges, their next turn enters Final Category Choice instead of ordinary
Category Choice. It still displays all six colored category buttons. The group selects the final
category aloud, and the reader taps it. The question screen then works exactly as it does for a
normal turn.

Correct on a final question changes the state to Winner and shows the player’s name, all six filled
wedges, and a Start New Game control. No score summary or next turn follows a winning answer.

Incorrect on a final question ends the turn. The summary appears, play passes to the next person,
and the fully qualified player may try another final question on that player's next turn.

### Skip Question

Skip marks the displayed question used, draws another unused question from the same category, keeps
the same reader and active player, and gives no score or turn change. It does not repeat the
question, change category, or silently select a substitute category. An exhausted category is a
blocking data error.

## Phone-only layout contract

The application supports portrait phone viewports only. The target minimum is 320 by 568 CSS
pixels. No desktop layout is designed or tested.

Common states should fit within `100dvh`, but the document retains normal vertical scrolling for
long questions and mobile refresh gestures. There is no horizontal scroll, no clipping, and no
truncated question or answer strings. Button text and category names use the full configured label.

Typography may use responsive CSS within an agreed readable range. Long questions and answers may
extend the page vertically. The app does not clip, shorten, paraphrase, or substitute that text.

The layout is therefore a data contract as well as a CSS contract. A question bank cannot be marked
ready until its longest question and answer have been checked at the minimum viewport.

## Current source inventory and first-bank decision

The acquired source cache contains two general-trivia candidates with source categories and source
difficulty. The first release does not use any age field.

| Source | Cached records | Source categories | Source difficulty | Content safety field | First-bank status |
| --- | ---: | ---: | --- | --- | --- |
| The Trivia API, `contentFilter=family`, text-choice | 7,993 | 10 | easy, medium, hard | family-filtered acquisition | Review candidate |
| Open Trivia DB full token harvest | 5,247 | 24 | easy, medium, hard | none | Not a first candidate |
| OpenBookQA, ARC, QASC, CommonsenseQA | science or reasoning datasets | no usable broad category taxonomy | corpus-level only or none | none | Not a first general bank |

The Trivia API cache has these source-category counts: film and TV 1,094; society and culture
1,012; science 1,005; geography 982; arts and literature 911; music 901; history 808; food and
drink 500; sport and leisure 452; and general knowledge 328. Its difficulty counts are 775 easy,
3,383 medium, and 3,835 hard. All cached records are source type `text_choice` and have
`isNiche: false`.

Open Trivia DB is less suitable for the first pass despite its larger taxonomy. Its cache contains
1,172 video-game questions, and it has no family-content filter or tags. Its
categories and difficulty are useful metadata, but the absence of a content-safety source filter
creates a larger review queue.

The first review sample should therefore come only from the cached, family-filtered The Trivia API
records. It should retain the six selected source labels, source difficulty, tags, and upstream ID
unchanged. It should not be marketed as Family or Adults. Age appropriateness is deferred to a
future pass, and no LLM classification runs in the first release.

### Stratified source-quality screening

The reproducible sample is at
`~/photosite-trivia-sources/work/trivia-api-review-sample-2026-08-25.json`. The selection script
is `~/photosite-trivia-sources/scripts/make_review_sample.py`. It selected three records from each
of six candidate source categories and each source difficulty, for 54 records total. Within every
category/difficulty stratum, it chooses the records with the lowest SHA-256 hash of upstream ID;
the selection is therefore stable and does not depend on a model.

The screen found usable general-trivia coverage, but it also found reasons not to bundle the raw
cache:

- **Answer-choice-dependent wording.** 587 of 7,993 records use `Which of these` or `Which of the
  following`. These are compatible with the approved design because the reader view will display
  and read every source choice. The source's correct answer and incorrect answers must therefore
  be retained, with their displayed order saved in game state before rendering.
- **Text that cannot be assumed to fit.** 39 prompts exceed 160 characters; 15 exceed 200; and 6
  answers exceed 120. The longest prompt is 447 characters and the longest answer is 278. The
  phone layout must measure reviewed records at the target viewport and reject any record that
  cannot fit without scrolling. It must not shorten these fields.
- **Source accuracy and editing defects.** The sample contains an incorrect nursery-rhyme label
  (`63a0399ac7d86251f9b65c8d`), a question that needs answer choices
  (`63989c285c9a75021f310486`), `Whitehouse` instead of `White House`
  (`622a1c3c7cc59eab6f95181e`), `Lewis Carrol` instead of `Lewis Carroll`
  (`622a1c3c7cc59eab6f951896`), and inconsistent capitalization and punctuation. A published bank
  needs record-level correction or rejection, with the upstream ID retained.
- **Content boundary.** The sample includes Nazi persecution in a *Schindler’s List* question
  (`62573efd9da29df7b05f7380`), nuclear-war plot material (`62573fc99da29df7b05f73ac`), execution
  history, religion, and obscure professional knowledge. These subjects may be included. No
  sexually explicit question appeared in the sample, and sexually explicit questions are excluded.
- **Difficulty is useful but imperfect.** An easy question asks for a botanical scientific name,
  while medium questions include school chemistry and an obscure invention term. The source level
  should be displayed and retained, but it does not settle whether a question belongs in the bank.

The screening decision is: do not use raw records directly; do not create Family or Adult banks
yet; and do not run LLM labeling. The next data step is a small human-reviewed export with six
chosen source categories, source difficulty and all answer choices retained, sexually-explicit-
content exclusion, and a fit check at the minimum phone viewport.

## Local data and JavaScript modules

The application is static. Questions live in JavaScript modules shipped with the page. It never
fetches questions at runtime.

Proposed files after approval:

```text
content/static/trivia/
  index.html
  trivia.css
  app.js
  state.js
  question-selector.js
  question-banks.js
  banks/
    trivia-api-review-sample.js
```

`question-banks.js` contains bank metadata and imports only the banks selected for release. Each
bank module exports data, not executable source acquisition code.

Each question has this required shape:

```js
{
  id: "family-history-000123",
  sourceCategory: "history",
  prompt: "...",
  answer: "...",
  incorrectAnswers: ["...", "...", "..."], // optional, preserved from the source
  sourceDifficulty: "easy", // optional, preserved from the source
  contentReview: "no-sexual-content", // required; explicit sexual material is ineligible
  source: "curated-bank-name"
}
```

The app displays `sourceDifficulty` when it exists. It shows the source choices when they exist,
in a saved randomized order that remains stable across refresh. The first version selects from the
bundled bank and category using the active player's selected source difficulties. It does not infer,
store, display, or filter age. Family and Adult bank labels are deferred to a later
age-appropriateness pass. No future label permits sexually explicit content.

The acquisition cache retains raw source data even when it lacks age metadata. A playable bank is
a reviewed export from that cache. The bank validator rejects duplicate question identifiers,
unknown source categories, absent prompts or answers, missing content approval, and a bank that
lacks at least one question in any of its six declared source categories.
A game that runs out of unused questions for the selected category displays a blocking error naming
the bank and category. It does not choose a different category, repeat a question, or call an API.

## URL and browser storage

The setup choices are shareable URL parameters. Runtime game state is local browser storage.

| Location | Data | Reason |
| --- | --- | --- |
| `?players=<comma-separated-player-ids>` | selected default people | Shareable setup choice. |
| `?difficulties=<player-id:levels;...>` | selected difficulty levels per person | Shareable setup choice. |
| `localStorage: trivia.config.v1` | last valid setup selection | Restores setup after a return visit. |
| `localStorage: trivia.game.v1` | active game state and used question identifiers | Restores a refresh during play. |

An unknown player identifier, duplicated player identifier, malformed difficulty selection,
unavailable local storage, or unsupported saved-state version is a visible error. The app does not
silently ignore or repair malformed state.

The saved game state contains: schema version, player difficulty selections, player scores,
shuffled turn order, active-turn index, current state name, current category, current question
identifier, answer visibility, used-question identifiers, and final-question status. It contains no
answers from the user, analytics, account data, or network identifiers.

## Errors and unsupported conditions

There are no fallbacks. Every expected failure has a plain error screen that names the failed
condition and provides only a safe return to setup when that does not discard an active game.

- Invalid bundled bank data: show the bank validation error.
- Fewer than two selected players: prevent start and state the required count.
- No unused question in a category: show bank and category identifiers.
- Corrupt or unsupported saved game: show the storage schema error and provide Start New Game.
- Storage write failure: show that the game cannot be saved; do not continue with a game that would
  lose turn state on refresh.
- A question too large for the screen: show its identifier and stop before partial rendering.
- A question missing content approval: reject the bank before play.

## Accessibility and interaction

Every control has a visible text label. Category buttons carry both color and category name, so
color is not the sole signal. Controls meet a 44 by 44 CSS-pixel minimum target. The active player,
reader, current category, and score result are text, not icon-only indicators. Focus order follows
the visual order, although the intended use is touch.

## Automated test plan

The prototype is ready for review only after these checks pass:

The prototype has Playwright browser tests, run against the built development preview. The test
suite uses a deterministic test bank and seeded random selection only in test mode; production
selection remains random.

1. Setup starts with all four people selected; Claire has Easy and Medium, while every other person
   has Easy, Medium, and Hard. Toggling a person affects only that person, and Start rejects fewer
   than two people or a selected person with no difficulty.
2. Start produces a permutation of the selected people and does not repeat an identifier.
3. Every category button selects an unused question from its own category and from the active
   player's selected difficulty set.
4. The question view shows the complete prompt, every supplied answer choice, complete correct
   answer, Hide Answer, source difficulty only when present, and no timer. Hide and Show preserve
   the answer-visibility state across a refresh.
6. Correct fills only the active player’s first empty wedge for that category; Incorrect changes no
   wedge; summary advances to the next shuffled person.
7. Skip replaces the question in the same category for the same player and never repeats a used
   question.
8. A player with six wedges enters final category choice; a correct final answer reaches Winner.
9. Refreshing every state restores the same active player, question, and score.
10. Valid setup URL parameters populate setup; malformed parameters show errors.
11. At 320 by 568 and 390 by 844, common states remain compact, horizontal scrolling never occurs,
    and long question content remains reachable through normal vertical scrolling.
12. Empty categories, invalid bank data, absent content review, exhausted difficulty/category
   combinations, storage failure, and oversized questions show their explicit errors instead of a
   replacement behavior.

The first prototype uses six exact Trivia API labels, with reversible presentation normalization:
Arts and Literature, Film and TV, Geography, History, Science, and Society and Culture.
