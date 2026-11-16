# Semester Week 12 Progress Report

## Completed Work

- **Fictional mock dataset** (`data/`), documented in `data/README.md`:
  - `profile.json`: one job seeker (Junior Data Analyst, Almaty). Skills are marked confirmed or unconfirmed; Power BI is claimed but not confirmed.
  - `vacancies.json`: 30 vacancies in Almaty, Astana, Shymkent and Karaganda, some remote, from intern to senior. Vacancy 27 deliberately contains a prompt-injection text for the later guardrail tests.
  - `skills.json`: 41 canonical skills, English and Russian aliases, and 26 "learnable in N days" relations between skills.
- **Dataset loader with validation** (`src/career_agent/data.py`):
  - pydantic models check every file when it is loaded: allowed cities and levels, salary ranges, unique ids;
  - every skill must exist in the skill list;
  - a broken file stops the program at start-up with a clear `DataError`, so tools never see bad data.
- **Three read-only tools** (`src/career_agent/tools.py`):
  - `get_profile()` returns the profile and separates confirmed from unconfirmed skills.
  - `search_vacancies(query, city, level, remote, limit)` searches by role words and skills. It understands Russian words and city names (for example "аналитик данных", "Алматы") and multi-word skills ("Power BI"). With no results it returns a hint to broaden the search, which the agent will use for replanning.
  - `analyze_match(vacancy_id)` returns *have / close / missing* skills, a deterministic score from 0 to 100, a recommendation (`apply` / `learn_then_apply` / `stretch` / `poor_fit`), the learning days and the level fit. The employer text is returned only under `employer_description_untrusted`.
- **Argument validation before execution.** `validate_args` uses strict pydantic models (`extra="forbid"`, strict int and bool, ranges, allowed values) and rejects malformed arguments before any tool code runs. `run_tool` always returns either a result or `{"error": code, "message": ...}` (`invalid_arguments`, `not_found`, `unknown_tool`), so a bad call does not crash the agent.
- **27 new tests** (`tests/test_tools.py`), 42 in total, all passing:
  - the dataset loads, and broken data fails fast;
  - alias normalisation;
  - search filters, Russian queries, multi-word skills, the empty result with a hint, and the limit;
  - 8 malformed-argument cases;
  - the match categories, ignoring unconfirmed skills, the poor-fit and level checks, determinism, an unknown vacancy;
  - the untrusted employer text;
  - an unknown tool.

## Important Commits

- Commit hash: see the commit "Week 12: mock dataset and validated read-only tools" in the history.
- Description: the dataset, the loader, `get_profile` / `search_vacancies` / `analyze_match`, argument validation and 27 tests.
- Link: https://github.com/Arito1/css4007-ai-agents-final/commits/main

## Current Functionality

- The tools work offline on the mock data. Examples:
  - `analyze_match(1)` gives score 100 and `apply`;
  - `analyze_match(3)` gives `learn_then_apply` with MySQL (3 days, from SQL) and Tableau (7 days, from Data Visualization);
  - `analyze_match(4)` gives `poor_fit` with Airflow, Spark and Docker missing;
  - `search_vacancies("Python backend intern", city="Astana")` returns no results and a hint to broaden the search.
- The CLI `ask` command still sends one request to Claude Haiku 5.5. The model does not call the tools yet: that is Week 13.

## Problems Encountered

- My first search matched any single word, so "Python backend intern" in Astana returned unrelated data-analyst internships.
- Multi-word skills ("Power BI", "REST API") were split into separate words and did not match.
- After a Windows update, Smart App Control blocked the native module of `jiter 0.19.0`, a dependency of the Anthropic SDK. All tests failed with "DLL load failed".
- Matching had to be explainable and must not count skills the user only claims.

## Solutions

- The query is split into role words, which must all appear in the title (or match the level or "remote"), and skill names, which rank the results.
- Multi-word skill names and aliases are detected first, longest first, before the query is split into words.
- I installed `jiter 0.18.0`, which the policy allows, and documented the workaround in the README. I did not change any system security settings.
- Matching uses only `confirmed` skills, and the "close" rule is a fixed table of skill relations with a 14-day limit. The same input always gives the same score, so the agent's decisions can be tested.

## What I Learned

- Validating data at the boundary with pydantic: strict types, `extra="forbid"` and custom validators. Validation errors become one tool error format instead of exceptions.
- Why deterministic tools are important in an agent: the LLM decides *what to do*, but facts such as the score and the skill gaps come from code. That makes the results reproducible and testable.
- Marking external text (employer descriptions) as untrusted as early as the data layer.

## Next Week

- Tool registry with JSON schemas for Claude; LLM tool selection; the first multi-step run (profile, then search, then match).
- Implement `build_learning_plan` and `draft_resume` (draft only), and the tool permission table (read / draft / consequential).
- Tests with a scripted fake LLM that requests tools in order.
