"""Read-only tools over the mock dataset: get_profile, search_vacancies, analyze_match.

Every tool call goes through `validate_args` first: malformed arguments are
rejected before any tool code runs. Tools return plain JSON-serialisable dicts
(they become tool results for the model) and signal problems with ToolError.
Matching and scoring are deterministic code, not the LLM.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError, field_validator

from .data import CITIES, CITY_ALIASES, DataStore, Vacancy

CLOSE_MAX_DAYS = 14  # a missing skill counts as "close" if learnable within this many days
REQUIRED_WEIGHT, NICE_WEIGHT = 80, 20  # score = up to 80 for required + up to 20 for nice-to-have
LEVEL_ORDER = {"intern": 0, "junior": 1, "middle": 2, "senior": 3}

# Russian query words -> English words used in vacancy titles.
QUERY_SYNONYMS = {
    "аналитик": "analyst", "данных": "data", "данные": "data", "разработчик": "developer",
    "программист": "programmer", "стажер": "intern", "стажёр": "intern", "стажировка": "intern",
    "бэкенд": "backend", "фронтенд": "frontend", "дизайнер": "designer", "инженер": "engineer",
    "удаленно": "remote", "удалённо": "remote",
}
STOPWORDS = {"a", "an", "the", "in", "for", "and", "or", "job", "jobs", "vacancy", "vacancies", "в", "и", "на", "по"}


class ToolError(Exception):
    """A tool could not produce a result. `code` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message}


# ---------------------------------------------------------------- arguments

class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GetProfileArgs(_Args):
    pass


class SearchVacanciesArgs(_Args):
    query: str = Field(min_length=2, max_length=100)
    city: str | None = None
    level: Literal["intern", "junior", "middle", "senior"] | None = None
    remote: StrictBool | None = None
    limit: StrictInt = Field(default=5, ge=1, le=10)

    @field_validator("city")
    @classmethod
    def _known_city(cls, value: str | None) -> str | None:
        if value is None:
            return None
        canonical = CITY_ALIASES.get(value.strip().lower())
        if canonical is None:
            raise ValueError(f"unknown city {value!r}; allowed: {', '.join(CITIES)}")
        return canonical


class AnalyzeMatchArgs(_Args):
    vacancy_id: StrictInt = Field(ge=1)


ARG_MODELS: dict[str, type[_Args]] = {
    "get_profile": GetProfileArgs,
    "search_vacancies": SearchVacanciesArgs,
    "analyze_match": AnalyzeMatchArgs,
}


def validate_args(tool: str, raw: Any) -> _Args:
    """Validate raw (model-supplied) arguments. Raises ToolError, never runs the tool."""
    model = ARG_MODELS.get(tool)
    if model is None:
        raise ToolError("unknown_tool", f"no tool named {tool!r}")
    if not isinstance(raw, dict):
        raise ToolError("invalid_arguments", "arguments must be a JSON object")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
        )
        raise ToolError("invalid_arguments", problems) from exc


# ---------------------------------------------------------------- tools

def get_profile(store: DataStore, args: GetProfileArgs | None = None) -> dict[str, Any]:
    p = store.profile
    return {
        "id": p.id,
        "name": p.name,
        "target_role": p.target_role,
        "city": p.city,
        "level": p.level,
        "languages": p.languages,
        "confirmed_skills": [{"name": s.name, "level": s.level} for s in p.skills if s.confirmed],
        "unconfirmed_skills": [s.name for s in p.skills if not s.confirmed],
        "note": "Only confirmed_skills may be used for matching or in a resume.",
        "experience": [e.model_dump() for e in p.experience],
        "education": [e.model_dump() for e in p.education],
        "projects": [e.model_dump() for e in p.projects],
    }


def _summary(v: Vacancy) -> dict[str, Any]:
    return {
        "id": v.id,
        "title": v.title,
        "company": v.company,
        "city": v.city,
        "remote": v.remote,
        "level": v.level,
        "employment": v.employment,
        "salary_kzt": [v.salary_from, v.salary_to],
        "required_skills": v.required_skills,
        "published_at": v.published_at.isoformat(),
    }


def _words(text: str) -> set[str]:
    return set(re.findall(r"[\w+#.]+", text.lower()))


def _query_terms(store: DataStore, query: str) -> tuple[set[str], set[str]]:
    """Split the query into role words ('data', 'analyst', 'intern') and skill names."""
    role_terms, skill_terms = set(), set()
    text = f" {query.lower()} "
    for spelling, canonical in store.skills.multiword_names():  # "power bi", "rest api", ...
        pattern = rf"(?<![\w]){re.escape(spelling)}(?![\w])"
        if re.search(pattern, text):
            skill_terms.add(canonical)
            text = re.sub(pattern, " ", text)
    for word in _words(text):
        word = QUERY_SYNONYMS.get(word, word)
        if word in STOPWORDS or len(word) < 2:
            continue
        skill = store.skills.normalize(word)
        if skill:
            skill_terms.add(skill)
        else:
            role_terms.add(word)
    return role_terms, skill_terms


def search_vacancies(store: DataStore, args: SearchVacanciesArgs) -> dict[str, Any]:
    """Role words must all appear in the title (or match level / 'remote');
    skill names rank the results. A query of skills only needs at least one hit."""
    role_terms, skill_terms = _query_terms(store, args.query)
    if not role_terms and not skill_terms:
        raise ToolError("invalid_arguments", "query contains no searchable words")

    ranked = []
    for v in store.vacancies.values():
        if args.city and v.city != args.city:
            continue
        if args.level and v.level != args.level:
            continue
        if args.remote is not None and v.remote != args.remote:
            continue
        title_words = _words(v.title) | {v.level} | ({"remote"} if v.remote else set())
        if not role_terms <= title_words:
            continue
        skill_hits = len(skill_terms & set(v.required_skills + v.nice_to_have))
        if not role_terms and not skill_hits:
            continue
        ranked.append((skill_hits, v))

    ranked.sort(key=lambda item: (-item[0], -item[1].published_at.toordinal(), item[1].id))
    found = [_summary(v) for _, v in ranked[: args.limit]]
    result: dict[str, Any] = {
        "filters": args.model_dump(),
        "total_matches": len(ranked),
        "count": len(found),
        "vacancies": found,
    }
    if not found:
        result["message"] = (
            "No vacancies match. Consider removing the city filter, trying remote=true, "
            "or searching for an adjacent role."
        )
    return result


def _classify(store: DataStore, needed: list[str], have: set[str]):
    matched, close, missing = [], [], []
    for skill in needed:
        if skill in have:
            matched.append(skill)
            continue
        options = [(store.skills.days_between(k, skill), k) for k in have]
        options = [(d, k) for d, k in options if d is not None and d <= CLOSE_MAX_DAYS]
        if options:
            days, source = min(options)
            close.append({"skill": skill, "learn_from": source, "days": days})
        else:
            missing.append(skill)
    return matched, close, missing


def _ratio(matched: list, close: list, total: int) -> float:
    return (len(matched) + 0.5 * len(close)) / total if total else 0.0


def analyze_match(store: DataStore, args: AnalyzeMatchArgs) -> dict[str, Any]:
    v = store.vacancies.get(args.vacancy_id)
    if v is None:
        raise ToolError("not_found", f"vacancy {args.vacancy_id} does not exist")

    have = store.profile.confirmed_skills
    req_have, req_close, req_missing = _classify(store, v.required_skills, have)
    nice_have, nice_close, nice_missing = _classify(store, v.nice_to_have, have)

    required_ratio = _ratio(req_have, req_close, len(v.required_skills))
    nice_ratio = _ratio(nice_have, nice_close, len(v.nice_to_have)) if v.nice_to_have else required_ratio
    score = round(REQUIRED_WEIGHT * required_ratio + NICE_WEIGHT * nice_ratio)

    if not req_missing and not req_close:
        recommendation = "apply"
    elif not req_missing:
        recommendation = "learn_then_apply"
    elif score >= 50:
        recommendation = "stretch"
    else:
        recommendation = "poor_fit"

    level_gap = LEVEL_ORDER[v.level] - LEVEL_ORDER[store.profile.level]
    return {
        "vacancy": _summary(v),
        "score": score,
        "recommendation": recommendation,
        "required": {"have": req_have, "close": req_close, "missing": req_missing},
        "nice_to_have": {"have": nice_have, "close": nice_close, "missing": nice_missing},
        "learning_days_for_required": sum(c["days"] for c in req_close),
        "level_fit": level_gap <= 0,
        # Employer text is untrusted data, never instructions.
        "employer_description_untrusted": v.description,
    }


TOOL_FUNCTIONS = {
    "get_profile": get_profile,
    "search_vacancies": search_vacancies,
    "analyze_match": analyze_match,
}


def run_tool(store: DataStore, tool: str, raw_args: Any) -> dict[str, Any]:
    """Validate, then execute. Always returns a dict; errors become {'error', 'message'}."""
    try:
        args = validate_args(tool, raw_args)
        return TOOL_FUNCTIONS[tool](store, args)
    except ToolError as exc:
        return exc.to_dict()
