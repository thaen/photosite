# Phone Trivia: technical design

## Status

This document specifies the application before implementation. It does not authorize a Trivia
screen, question-bank import, or S3 publication. The names, state transitions, and test cases
below are the proposed contract for review.

## Product boundary

The product is a pass-the-phone trivia game for people sitting together. It uses the familiar
six-category, collect-one-marker-per-category, then answer-a-final-question structure. It has no
board, movement, die, accounts, server, network play, API calls, desktop layout, or copied visual
identity. The visible product name is **Trivia**.

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

At least two people must be selected. Pressing Start Game with fewer than two selected people
shows a blocking, plain-language error on the setup screen: `Select at least two players.` The app
does not silently reselect a person.

### Question-bank selection

The screen also has one large button for each locally bundled question bank. A bank button shows
its name and a short audience label from the bank metadata, such as `Family` or `Adults`. Exactly
one bank is selected.

The first bank in the registry with `default: true` is selected when the URL does not name a bank.
If the registry has no default bank, or the selected bank is absent or invalid, the app shows a
blocking error. It does not select a different bank without showing the problem.

### Start Game

Start Game creates a new game, uses the selected bank and people, performs a Fisher–Yates shuffle
of the selected player identifiers, saves the game state, and enters the first category-choice
screen. The shuffle order is the turn order for the whole game.

Starting a new game replaces a saved unfinished game. The setup screen must ask for confirmation
when an unfinished game exists, because replacement loses the saved score and used-question list.

## Category model

Every supported bank uses the same six canonical category identifiers. The first bank can choose
the visible labels and colors, but the initial proposed set is:

| Identifier | Visible label | Color token |
| --- | --- | --- |
| `history` | History | orange |
| `science` | Science and nature | blue |
| `arts` | Arts and entertainment | pink |
| `places` | Places | green |
| `people` | People and culture | purple |
| `everyday` | Everyday life | yellow |

The category registry, rather than a question's free-form category text, defines the color and
label shown in the app. Each question has exactly one canonical category. The score display has
one colored wedge per canonical category.

## Turn flow

The app uses a finite state machine. A fresh page reload restores the saved state and redraws the
same state; it does not reroll the order or choose a new question.

### 1. Category choice

The page identifies the active player and reader in text such as `Alice’s turn — hand the phone to
Bob.` It displays six large category buttons, each with its category color and full text label.
Bob reads the choices. Alice chooses aloud. Bob taps the chosen category.

Before displaying a question, the app selects one unused question in the selected bank and category.
Question selection is random within the eligible set. It records the selected question identifier
in the saved state before rendering it, so a refresh cannot draw a different question.

### 2. Question and judging

The question screen has these items in this order, all visible without scrolling:

1. Active-player and reader names.
2. Category color and category name.
3. Full question text.
4. Full answer text.
5. A difficulty label only when the question has a difficulty value.
6. Correct, Incorrect, and Skip Question buttons.

Bob reads the question to Alice, hears the answer, consults the visible answer, and presses Correct
or Incorrect. The application does not attempt automatic answer matching.

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

The required behavior after an incorrect final question needs approval. The proposed rule is that
the player remains fully qualified, the summary appears, and play passes to the next person. The
player may try another final question on a later turn. This rule avoids a one-question elimination
and keeps the normal phone handoff intact.

### Skip Question: decision needed

The required Skip Question button has two plausible meanings, and implementation must wait for a
decision:

1. **Recommended:** Skip marks the displayed question used, draws another unused question from the
   same category, keeps the same reader and active player, and gives no score or turn change.
2. **Alternative:** Skip marks the displayed question used, gives no score, and proceeds directly
   to the score summary and next player.

The recommended rule avoids a turn that ends before the active player has a chance to answer. It
also makes question-bank depth visible, because repeated skips can exhaust a category.

## Phone-only layout contract

The application supports portrait phone viewports only. The target minimum is 320 by 568 CSS
pixels. No desktop layout is designed or tested.

Each state fits within `100dvh` with `overflow: hidden` on the document and its application root.
There are no scroll containers, horizontal scroll, accordions containing required information, or
truncated question or answer strings. Button text and category names use the full configured label.

Typography may use responsive CSS within an agreed readable range. If a question or answer cannot
fit in the fixed screen without scrolling or making text smaller than that range, the app displays
a blocking data error that names the question identifier. It does not clip, shorten, paraphrase,
or substitute that question.

The layout is therefore a data contract as well as a CSS contract. A question bank cannot be marked
ready until its longest question and answer have been checked at the minimum viewport.

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
    family.js
    adults.js
```

`question-banks.js` contains bank metadata and imports only the banks selected for release. Each
bank module exports data, not executable source acquisition code.

Each question has this required shape:

```js
{
  id: "family-history-000123",
  category: "history",
  prompt: "...",
  answer: "...",
  difficulty: "easy", // optional
  audience: { minAge: 8, maxAge: null }, // optional
  source: "curated-bank-name"
}
```

The app displays `difficulty` when it exists. The first version selects from the chosen bank and
category; it does not infer a child’s age from a name. A future setup option may use the optional
audience data to filter a bank, but it needs a separate product decision about each player's age.

The bank validator rejects duplicate question identifiers, unknown categories, absent prompts or
answers, and a bank that lacks at least one question in any canonical category. A game that runs
out of unused questions for the selected category displays a blocking error naming the bank and
category. It does not choose a different category, repeat a question, or call an API.

## URL and browser storage

The setup choices are shareable URL parameters. Runtime game state is local browser storage.

| Location | Data | Reason |
| --- | --- | --- |
| `?bank=<bank-id>` | selected question bank | Shareable setup choice. |
| `?players=<comma-separated-player-ids>` | selected default people | Shareable setup choice. |
| `localStorage: trivia.config.v1` | last valid setup selection | Restores setup after a return visit. |
| `localStorage: trivia.game.v1` | active game state and used question identifiers | Restores a refresh during play. |

An unknown bank identifier, unknown player identifier, duplicated player identifier, malformed
parameter, unavailable local storage, or unsupported saved-state version is a visible error. The
app does not silently ignore or repair malformed state.

The saved game state contains: schema version, chosen bank, player scores, shuffled turn order,
active-turn index, current state name, current category, current question identifier, used-question
identifiers, and final-question status. It contains no answers from the user, analytics, account
data, or network identifiers.

## Errors and unsupported conditions

There are no fallbacks. Every expected failure has a plain error screen that names the failed
condition and provides only a safe return to setup when that does not discard an active game.

- No selected bank or invalid bank data: show the bank validation error.
- Fewer than two selected players: prevent start and state the required count.
- No unused question in a category: show bank and category identifiers.
- Corrupt or unsupported saved game: show the storage schema error and provide Start New Game.
- Storage write failure: show that the game cannot be saved; do not continue with a game that would
  lose turn state on refresh.
- A question too large for the screen: show its identifier and stop before partial rendering.

## Accessibility and interaction

Every control has a visible text label. Category buttons carry both color and category name, so
color is not the sole signal. Controls meet a 44 by 44 CSS-pixel minimum target. The active player,
reader, current category, and score result are text, not icon-only indicators. Focus order follows
the visual order, although the intended use is touch.

## Test plan for the later prototype

The prototype is ready for review only after these checks pass:

1. Setup starts with Nora, Claire, Cori, and Ethan selected and a bank selected.
2. Tapping any person toggles only that person; Start rejects fewer than two selections.
3. Start produces a permutation of the selected people and does not repeat an identifier.
4. Every category button selects an unused question from its own category.
5. The question view shows the complete prompt, complete answer, and difficulty only when present.
6. Correct fills only the active player’s first empty wedge for that category; Incorrect changes no
   wedge; summary advances to the next shuffled person.
7. Skip follows the approved rule and never repeats a used question.
8. A player with six wedges enters final category choice; a correct final answer reaches Winner.
9. Refreshing every state restores the same active player, question, and score.
10. Valid setup URL parameters populate setup; malformed parameters show errors.
11. At 320 by 568 and 390 by 844, every state has no vertical or horizontal scroll and all required
    controls are reachable.
12. Empty categories, invalid bank data, exhausted categories, storage failure, and oversized
    questions show their explicit errors instead of a replacement behavior.

## Decisions requested before implementation

1. Is the proposed retry-on-a-later-turn rule correct after an incorrect final question?
2. Should Skip replace the question for the same player, or end the turn?
3. Are the six proposed category labels right for the first bank, or should the bank choose its
   own labels while retaining stable category identifiers?
4. Should the first playable bank be family-only, adult-only, or contain both as separate buttons?
5. Should the first release have a time limit, or should the reader control the pace without one?
