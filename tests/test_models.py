from __future__ import annotations

import pytest
from pydantic import ValidationError

from edge_validation.models import RequirementResult, TaskProfile, TestRunSummary


@pytest.mark.parametrize("samples", [10, 11, 128, 1024, 99_999, 100_000])
def test_profile_accepts_sample_boundaries(samples: int) -> None:
    profile = TaskProfile(name="valid", sample_count=samples, noise_sigma=0.1, drift_limit=0.2)
    assert profile.sample_count == samples


@pytest.mark.parametrize("samples", [-1, 0, 1, 9, 100_001, 1_000_000])
def test_profile_rejects_sample_boundaries(samples: int) -> None:
    with pytest.raises(ValidationError):
        TaskProfile(name="invalid", sample_count=samples, noise_sigma=0.1, drift_limit=0.2)


@pytest.mark.parametrize("noise", [0.0, 0.01, 0.5, 0.999, 1.0])
def test_profile_accepts_noise_boundaries(noise: float) -> None:
    assert (
        TaskProfile(name="valid", sample_count=10, noise_sigma=noise, drift_limit=0.2).noise_sigma
        == noise
    )


@pytest.mark.parametrize("noise", [-10.0, -0.001, 1.001, 2.0])
def test_profile_rejects_noise_boundaries(noise: float) -> None:
    with pytest.raises(ValidationError):
        TaskProfile(name="invalid", sample_count=10, noise_sigma=noise, drift_limit=0.2)


@pytest.mark.parametrize("drift", [0.001, 0.2, 1.0, 4.999, 5.0])
def test_profile_accepts_drift_boundaries(drift: float) -> None:
    assert (
        TaskProfile(name="valid", sample_count=10, noise_sigma=0.1, drift_limit=drift).drift_limit
        == drift
    )


@pytest.mark.parametrize("drift", [-1.0, 0.0, 5.001, 10.0])
def test_profile_rejects_drift_boundaries(drift: float) -> None:
    with pytest.raises(ValidationError):
        TaskProfile(name="invalid", sample_count=10, noise_sigma=0.1, drift_limit=drift)


@pytest.mark.parametrize("name", ["", " ", "   ", "x" * 65])
def test_profile_rejects_invalid_names(name: str) -> None:
    with pytest.raises(ValidationError):
        TaskProfile(name=name, sample_count=10, noise_sigma=0.1, drift_limit=0.2)


def test_release_recommendation_go() -> None:
    summary = TestRunSummary("run", "now", 1.0, 2, 2, 0, 0)
    assert summary.pass_rate == 1.0
    assert summary.release_recommendation == "GO"


def test_release_recommendation_no_go() -> None:
    summary = TestRunSummary("run", "now", 1.0, 2, 1, 1, 0)
    assert summary.release_recommendation == "NO-GO"


def test_release_recommendation_conditional() -> None:
    blocked = RequirementResult("SYS-001", "BLOCKED", (), "hardware unavailable")
    summary = TestRunSummary("run", "now", 1.0, 1, 1, 0, 0, [blocked])
    assert summary.release_recommendation == "CONDITIONAL"


