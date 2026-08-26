"""Build the served Trivia bank from the complete cached Trivia API response."""

import json
from pathlib import Path

source = Path("/Users/ethanjohn/photosite-trivia-sources/cache/apis/the-trivia-api-family-text-choice.json")
output = Path(__file__).resolve().parents[1] / "content/static/trivia/bank.js"

if not source.is_file():
    raise FileNotFoundError(source)

cache = json.loads(source.read_text())
questions = cache["questions"]
if len(questions) != cache["questionCount"]:
    raise ValueError("The cache question count does not match its records.")

output.write_text("window.TRIVIA_QUESTIONS = " + json.dumps(questions, ensure_ascii=False) + ";\n")
