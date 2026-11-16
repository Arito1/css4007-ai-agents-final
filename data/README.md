# Mock dataset

All data here is **fictional**: the people, companies, vacancies and salaries are invented for the course project. Nothing here was taken from real job sites or real users.

| File | Content |
|---|---|
| `skills.json` | Canonical skill names, aliases (English/Russian spellings → canonical name) and skill relations. A relation `{a, b, days}` means: someone who knows `a` can learn `b` in about `days` days (and the other way round). |
| `profile.json` | One job-seeker profile. Only skills with `"confirmed": true` may be used by the agent (matching, resume). Unconfirmed skills are claims the user has not verified. |
| `vacancies.json` | 30 vacancies in Almaty, Astana, Shymkent and Karaganda, some remote. `description` is free text written by an "employer" and is treated as **untrusted** input. Vacancy 27 deliberately contains a prompt-injection attempt for the guardrail tests. |

The dataset is validated when it is loaded (`career_agent.data.load_store`). Every skill a vacancy or the profile mentions must exist in `skills.json`, and vacancy ids must be unique.
