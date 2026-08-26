(() => {
  if (!Array.isArray(window.TRIVIA_QUESTIONS)) {
    throw new Error("Trivia question bank is missing.");
  }
  for (const question of window.TRIVIA_QUESTIONS) {
    question.sourceCategory = question.category;
    question.sourceDifficulty = question.difficulty;
  }
})();
