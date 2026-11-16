"""Week 12 tests: mock dataset and the read-only tools. Fully offline."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from career_agent.data import DEFAULT_DATA_DIR, DataError, load_store
from career_agent.tools import run_tool


@pytest.fixture(scope="module")
def store():
    return load_store()


def search(store, **args):
    return run_tool(store, "search_vacancies", args)


def ids(result):
    return [v["id"] for v in result["vacancies"]]


# ------------------------------------------------------------ dataset

def test_dataset_loads_and_is_consistent(store):
    assert len(store.vacancies) == 30
    assert "Python" in store.profile.confirmed_skills
    assert "Power BI" not in store.profile.confirmed_skills  # claimed but unconfirmed


def test_skill_aliases_normalize(store):
    assert store.skills.normalize("postgres") == "PostgreSQL"
    assert store.skills.normalize("Эксель") == "Excel"
    assert store.skills.normalize("cobol") is None


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    target = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIR, target)
    return target


def test_unknown_skill_in_dataset_fails_fast(data_copy):
    vacancies = json.loads((data_copy / "vacancies.json").read_text(encoding="utf-8"))
    vacancies[0]["required_skills"].append("Cobol")
    (data_copy / "vacancies.json").write_text(json.dumps(vacancies), encoding="utf-8")
    with pytest.raises(DataError, match="Cobol"):
        load_store(data_copy)


def test_duplicate_vacancy_id_fails_fast(data_copy):
    vacancies = json.loads((data_copy / "vacancies.json").read_text(encoding="utf-8"))
    vacancies[1]["id"] = vacancies[0]["id"]
    (data_copy / "vacancies.json").write_text(json.dumps(vacancies), encoding="utf-8")
    with pytest.raises(DataError, match="duplicate"):
        load_store(data_copy)


# ------------------------------------------------------------ get_profile

def test_get_profile_separates_unconfirmed_skills(store):
    profile = run_tool(store, "get_profile", {})
    confirmed = {s["name"] for s in profile["confirmed_skills"]}
    assert "Power BI" not in confirmed
    assert profile["unconfirmed_skills"] == ["Power BI"]


def test_get_profile_rejects_unexpected_arguments(store):
    result = run_tool(store, "get_profile", {"user_id": "someone-else"})
    assert result["error"] == "invalid_arguments"


# ------------------------------------------------------------ search_vacancies

def test_search_with_city_alias_and_role_words(store):
    result = search(store, query="Junior Data Analyst", city="Алматы")
    assert set(ids(result)) == {1, 27}
    assert all(v["city"] == "Almaty" for v in result["vacancies"])


def test_search_understands_russian_query(store):
    result = search(store, query="аналитик данных", level="intern")
    assert ids(result) and all(v["level"] == "intern" for v in result["vacancies"])


def test_search_multiword_skill(store):
    result = search(store, query="analyst Power BI", city="Almaty")
    assert ids(result)[0] in {2, 21}  # vacancies that require Power BI come first


def test_search_without_results_returns_hint(store):
    result = search(store, query="Python backend intern", city="Astana")
    assert result["count"] == 0 and result["vacancies"] == []
    assert "remote" in result["message"]


def test_search_respects_limit_and_remote_filter(store):
    result = search(store, query="analyst", remote=False, limit=2)
    assert result["count"] == 2 and result["total_matches"] > 2
    assert all(not v["remote"] for v in result["vacancies"])


@pytest.mark.parametrize(
    "args",
    [
        {},                                         # query is required
        {"query": "a"},                             # too short
        {"query": "analyst", "limit": 50},          # out of range
        {"query": "analyst", "limit": "5"},         # wrong type (strict int)
        {"query": "analyst", "city": "Taraz"},      # unknown city
        {"query": "analyst", "level": "lead"},      # not an allowed value
        {"query": "analyst", "remote": "yes"},      # wrong type (strict bool)
        {"query": "analyst", "salary": 100},        # unknown field
    ],
)
def test_search_rejects_malformed_arguments(store, args):
    assert search(store, **args)["error"] == "invalid_arguments"


# ------------------------------------------------------------ analyze_match

def test_match_perfect_fit_recommends_apply(store):
    result = run_tool(store, "analyze_match", {"vacancy_id": 1})
    assert result["score"] == 100
    assert result["recommendation"] == "apply"
    assert result["required"]["missing"] == [] and result["required"]["close"] == []


def test_match_close_skills_recommend_learning(store):
    result = run_tool(store, "analyze_match", {"vacancy_id": 3})
    close = {c["skill"]: c for c in result["required"]["close"]}
    assert set(close) == {"MySQL", "Tableau"}
    assert close["MySQL"]["learn_from"] == "SQL"
    assert result["learning_days_for_required"] == 3 + 7
    assert result["recommendation"] == "learn_then_apply"


def test_match_ignores_unconfirmed_skills(store):
    result = run_tool(store, "analyze_match", {"vacancy_id": 2})  # requires Power BI
    assert "Power BI" not in result["required"]["have"]
    assert result["required"]["close"][0]["skill"] == "Power BI"


def test_match_poor_fit_and_level(store):
    result = run_tool(store, "analyze_match", {"vacancy_id": 4})
    assert result["recommendation"] == "poor_fit"
    assert set(result["required"]["missing"]) == {"Airflow", "Spark", "Docker"}
    assert result["level_fit"] is False  # middle vacancy, junior profile


def test_match_is_deterministic_and_bounded(store):
    for vacancy_id in store.vacancies:
        first = run_tool(store, "analyze_match", {"vacancy_id": vacancy_id})
        assert first == run_tool(store, "analyze_match", {"vacancy_id": vacancy_id})
        assert 0 <= first["score"] <= 100


def test_match_unknown_vacancy_is_not_found(store):
    assert run_tool(store, "analyze_match", {"vacancy_id": 999})["error"] == "not_found"
    assert run_tool(store, "analyze_match", {"vacancy_id": "1"})["error"] == "invalid_arguments"


def test_match_marks_employer_text_as_untrusted(store):
    result = run_tool(store, "analyze_match", {"vacancy_id": 27})
    assert "ignore all previous instructions" in result["employer_description_untrusted"].lower()
    assert "description" not in result  # only exposed under the explicit 'untrusted' key


def test_unknown_tool_is_rejected(store):
    assert run_tool(store, "delete_profile", {})["error"] == "unknown_tool"
