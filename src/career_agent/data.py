"""Mock dataset: loading, validation and skill normalisation.

The data files live in `data/` (all fictional). Everything is validated on load,
so tools can trust the in-memory objects. A broken file fails fast with DataError.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

City = Literal["Almaty", "Astana", "Shymkent", "Karaganda"]
Level = Literal["intern", "junior", "middle", "senior"]
CITIES: tuple[str, ...] = ("Almaty", "Astana", "Shymkent", "Karaganda")
LEVELS: tuple[str, ...] = ("intern", "junior", "middle", "senior")

# Accepted spellings for cities (lower-case) -> canonical name.
CITY_ALIASES: dict[str, str] = {
    "almaty": "Almaty", "алматы": "Almaty", "alma-ata": "Almaty", "алма-ата": "Almaty",
    "astana": "Astana", "астана": "Astana", "nur-sultan": "Astana", "нур-султан": "Astana",
    "shymkent": "Shymkent", "шымкент": "Shymkent",
    "karaganda": "Karaganda", "караганда": "Karaganda", "karagandy": "Karaganda",
}

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class DataError(RuntimeError):
    """The dataset is missing or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProfileSkill(_Strict):
    name: str
    level: str
    confirmed: bool


class Experience(_Strict):
    title: str
    company: str
    start: str
    end: str | None = None
    summary: str


class Education(_Strict):
    degree: str
    institution: str


class Project(_Strict):
    title: str
    summary: str


class Profile(_Strict):
    id: str
    name: str
    target_role: str
    city: City
    level: Level
    languages: list[str]
    skills: list[ProfileSkill]
    experience: list[Experience] = []
    education: list[Education] = []
    projects: list[Project] = []

    @property
    def confirmed_skills(self) -> set[str]:
        return {s.name for s in self.skills if s.confirmed}


class Vacancy(_Strict):
    id: int = Field(gt=0)
    title: str
    company: str
    city: City
    remote: bool
    level: Level
    employment: Literal["full-time", "part-time", "internship"]
    salary_from: int | None = Field(default=None, ge=0)
    salary_to: int | None = Field(default=None, ge=0)
    required_skills: list[str] = Field(min_length=1)
    nice_to_have: list[str] = []
    description: str  # free text from the "employer": UNTRUSTED
    published_at: date

    @model_validator(mode="after")
    def _salary_range(self) -> "Vacancy":
        if self.salary_from and self.salary_to and self.salary_from > self.salary_to:
            raise ValueError("salary_from is greater than salary_to")
        return self


class Relation(_Strict):
    a: str
    b: str
    days: int = Field(gt=0, le=90)


class SkillsFile(_Strict):
    skills: list[str]
    aliases: dict[str, str]
    relations: list[Relation]


class SkillGraph:
    """Canonical skills, aliases and 'learnable in N days' relations (undirected)."""

    def __init__(self, spec: SkillsFile):
        self.canonical = set(spec.skills)
        self._lookup = {s.lower(): s for s in spec.skills}
        for alias, target in spec.aliases.items():
            if target not in self.canonical:
                raise DataError(f"alias {alias!r} points to unknown skill {target!r}")
            self._lookup[alias.lower()] = target
        self._days: dict[str, dict[str, int]] = {s: {} for s in self.canonical}
        for rel in spec.relations:
            for skill in (rel.a, rel.b):
                if skill not in self.canonical:
                    raise DataError(f"relation uses unknown skill {skill!r}")
            self._days[rel.a][rel.b] = rel.days
            self._days[rel.b][rel.a] = rel.days

    def normalize(self, name: str) -> str | None:
        """Canonical skill name for any known spelling, or None if unknown."""
        return self._lookup.get(name.strip().lower())

    def multiword_names(self) -> list[tuple[str, str]]:
        """(lower-case spelling, canonical) for names with spaces, longest first."""
        items = [(k, v) for k, v in self._lookup.items() if " " in k]
        return sorted(items, key=lambda kv: -len(kv[0]))

    def days_between(self, known: str, target: str) -> int | None:
        """Days to learn `target` for someone who knows `known` (direct relations only)."""
        return self._days.get(known, {}).get(target)


@dataclass(frozen=True)
class DataStore:
    profile: Profile
    vacancies: dict[int, Vacancy]
    skills: SkillGraph


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"missing data file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"invalid JSON in {path.name}: {exc}") from exc


def _canonical_skills(graph: SkillGraph, names: list[str], where: str) -> list[str]:
    result = []
    for name in names:
        canonical = graph.normalize(name)
        if canonical is None:
            raise DataError(f"{where}: unknown skill {name!r} (add it to skills.json)")
        result.append(canonical)
    return result


def load_store(data_dir: str | Path | None = None) -> DataStore:
    """Load and validate profile, vacancies and skills from `data_dir`."""
    folder = Path(data_dir or os.environ.get("CAREER_AGENT_DATA_DIR") or DEFAULT_DATA_DIR)
    try:
        graph = SkillGraph(SkillsFile.model_validate(_read_json(folder / "skills.json")))
        profile = Profile.model_validate(_read_json(folder / "profile.json"))
        raw_vacancies = _read_json(folder / "vacancies.json")
        if not isinstance(raw_vacancies, list):
            raise DataError("vacancies.json must contain a list")
        vacancies_list = [Vacancy.model_validate(v) for v in raw_vacancies]
    except ValidationError as exc:
        raise DataError(f"invalid dataset: {exc}") from exc

    skills = [
        s.model_copy(update={"name": n})
        for s, n in zip(profile.skills, _canonical_skills(graph, [s.name for s in profile.skills], "profile"))
    ]
    profile = profile.model_copy(update={"skills": skills})

    vacancies: dict[int, Vacancy] = {}
    for v in vacancies_list:
        if v.id in vacancies:
            raise DataError(f"duplicate vacancy id {v.id}")
        vacancies[v.id] = v.model_copy(update={
            "required_skills": _canonical_skills(graph, v.required_skills, f"vacancy {v.id}"),
            "nice_to_have": _canonical_skills(graph, v.nice_to_have, f"vacancy {v.id}"),
        })
    return DataStore(profile=profile, vacancies=vacancies, skills=graph)
