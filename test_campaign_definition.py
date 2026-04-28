from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("QUANTMAP_LAB_ROOT", str(REPO_ROOT))


def _campaign_definition_module():
    try:
        return importlib.import_module("src.campaign_definition")
    except ModuleNotFoundError as exc:  # pragma: no cover - red stage only
        pytest.fail(f"src.campaign_definition is missing: {exc}")
        raise


def _baseline() -> dict[str, object]:
    return {
        "campaign_id": "baseline",
        "config": {
            "context_size": 4096,
            "n_gpu_layers": 999,
            "flash_attn": True,
            "jinja": True,
            "threads": 16,
            "threads_batch": 16,
            "threads_http": 1,
            "ubatch_size": 512,
            "batch_size": 2048,
            "mmap": True,
            "mlock": False,
            "cont_batching": True,
            "defrag_thold": 0.1,
            "kv_cache_type_k": "f16",
            "kv_cache_type_v": "f16",
        },
    }


# ---------------------------------------------------------------------------
# load_baseline / load_campaign
# ---------------------------------------------------------------------------

def test_load_baseline_success(tmp_path: Path) -> None:
    mod = _campaign_definition_module()
    baseline_path = tmp_path / "baseline.yaml"
    payload = {"config": {"threads": 8}, "requests": {"a": "a.json"}}
    baseline_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    loaded = mod.load_baseline(baseline_path)

    assert loaded == payload


def test_load_baseline_missing_file(tmp_path: Path) -> None:
    mod = _campaign_definition_module()

    with pytest.raises(FileNotFoundError, match="baseline.yaml not found"):
        mod.load_baseline(tmp_path / "missing.yaml")


def test_load_campaign_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _campaign_definition_module()
    campaigns_dir = tmp_path / "campaigns"
    campaigns_dir.mkdir()
    campaign_path = campaigns_dir / "C01_threads.yaml"
    payload = {"campaign_id": "C01_threads", "variable": "threads", "values": [8, 16]}
    campaign_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    monkeypatch.setattr(mod, "CAMPAIGNS_DIR", campaigns_dir)

    loaded = mod.load_campaign("C01_threads")

    assert loaded == payload


def test_load_campaign_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _campaign_definition_module()
    campaigns_dir = tmp_path / "campaigns"
    campaigns_dir.mkdir()
    monkeypatch.setattr(mod, "CAMPAIGNS_DIR", campaigns_dir)

    with pytest.raises(FileNotFoundError, match="Campaign YAML not found"):
        mod.load_campaign("missing_campaign")


# ---------------------------------------------------------------------------
# validate_campaign_purity
# ---------------------------------------------------------------------------

def test_purity_valid_standard_campaign() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "threads", "values": [8, 16]}

    variable = mod.validate_campaign_purity(baseline, campaign)

    assert variable == "threads"


def test_purity_valid_interaction_campaign() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "C08_interaction",
        "variable": "interaction",
        "values": [{"overrides": {"threads": 24}}],
    }

    variable = mod.validate_campaign_purity(baseline, campaign)

    assert variable == "interaction"


def test_purity_valid_auto_generated_campaign() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "AUTO_01",
        "variable": "threads",
        "values": [24],
        "auto_generated": True,
    }

    variable = mod.validate_campaign_purity(baseline, campaign)

    assert variable == "threads"


def test_purity_missing_variable_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "values": [8, 16]}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no variable"):
        mod.validate_campaign_purity(baseline, campaign)


def test_purity_null_variable_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": None, "values": [8, 16]}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no variable"):
        mod.validate_campaign_purity(baseline, campaign)


def test_purity_empty_variable_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "", "values": [8, 16]}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no variable"):
        mod.validate_campaign_purity(baseline, campaign)


def test_purity_whitespace_variable_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "   ", "values": [8, 16]}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no variable"):
        mod.validate_campaign_purity(baseline, campaign)


def test_purity_missing_values_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "threads", "values": []}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no values to sweep"):
        mod.validate_campaign_purity(baseline, campaign)


def test_purity_interaction_without_values_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C08_interaction", "variable": "interaction", "values": []}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no values to sweep"):
        mod.validate_campaign_purity(baseline, campaign)


def test_purity_auto_generated_without_values_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "AUTO_01",
        "variable": "threads",
        "values": [],
        "auto_generated": True,
    }

    with pytest.raises(mod.CampaignPurityViolationError, match="has no values to sweep"):
        mod.validate_campaign_purity(baseline, campaign)


def test_purity_unknown_variable_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C99_unknown", "variable": "unknown_flag", "values": [1]}

    with pytest.raises(mod.CampaignPurityViolationError, match="is not a field in baseline.yaml config section"):
        mod.validate_campaign_purity(baseline, campaign)


# ---------------------------------------------------------------------------
# build_config_list
# ---------------------------------------------------------------------------

def test_build_normal_scalar_sweep() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "threads", "values": [32]}

    configs = mod.build_config_list(baseline, campaign)

    assert configs[0]["config_id"] == "C01_threads_32"
    assert configs[0]["variable_name"] == "threads"
    assert configs[0]["variable_value"] == 32
    assert configs[0]["full_config"]["threads"] == 32
    assert "cpu_affinity_mask" in configs[0]
    assert configs[0]["cpu_affinity_mask"] is None
    assert "--threads" in configs[0]["server_args"]
    assert configs[0]["server_args"][configs[0]["server_args"].index("--threads") + 1] == "32"


def test_build_interaction_override() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "C08_interaction",
        "variable": "interaction",
        "values": [
            {
                "config_id": "C08_combo",
                "overrides": {
                    "threads": 24,
                    "n_parallel": 2,
                },
            }
        ],
    }

    configs = mod.build_config_list(baseline, campaign)

    assert configs[0]["config_id"] == "C08_combo"
    assert configs[0]["full_config"]["threads"] == 24
    assert configs[0]["full_config"]["n_parallel"] == 2
    assert "--parallel" in configs[0]["server_args"]


def test_build_cpu_affinity() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "C17_affinity",
        "variable": "cpu_affinity",
        "values": ["p_cores_only", "all_cores"],
        "cpu_affinity_details": {"p_cores_only": "0x00FF"},
    }

    configs = mod.build_config_list(baseline, campaign)

    assert configs[0]["config_id"].startswith("C17_affinity_p_cores_only")
    assert configs[0]["full_config"]["_cpu_affinity"] == "p_cores_only"
    assert configs[0]["cpu_affinity_mask"] == "0x00FF"
    assert configs[1]["config_id"].startswith("C17_affinity_all_cores")
    assert configs[1]["cpu_affinity_mask"] is None


def test_build_cpu_affinity_missing_details() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "C17_affinity",
        "variable": "cpu_affinity",
        "values": ["p_cores_only"],
    }

    with pytest.raises(mod.CampaignPurityViolationError, match="cpu_affinity_details is missing"):
        mod.build_config_list(baseline, campaign)


def test_build_cpu_affinity_unknown_key() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "C17_misspelled",
        "variable": "cpu_affinity",
        "values": ["p_cores_onyl"],  # misspelled
        "cpu_affinity_details": {"p_cores_only": "0x00FF"},
    }

    with pytest.raises(mod.CampaignPurityViolationError, match="has no affinity mask for key"):
        mod.build_config_list(baseline, campaign)


def test_build_kv_cache_mirror() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "C03_kv_cache_type_k",
        "variable": "kv_cache_type_k",
        "values": ["q8_0"],
        "kv_mirror_v": True,
    }

    configs = mod.build_config_list(baseline, campaign)

    assert configs[0]["config_id"].startswith("C03_kv_cache_type_k_q8_0")
    assert configs[0]["full_config"]["kv_cache_type_k"] == "q8_0"
    assert configs[0]["full_config"]["kv_cache_type_v"] == "q8_0"
    assert "--cache-type-k" in configs[0]["server_args"]
    assert "--cache-type-v" in configs[0]["server_args"]


def test_build_config_id_collision_resistant() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    shared_prefix = "very_long_value_name_"
    campaign = {
        "campaign_id": "C01_threads",
        "variable": "threads",
        "values": [f"{shared_prefix}{suffix}" for suffix in ("alpha", "beta")],
    }

    configs = mod.build_config_list(baseline, campaign)

    assert len(configs) == 2
    assert configs[0]["config_id"] != configs[1]["config_id"]
    # Both should contain the hash segment since prefix > 12 chars
    assert "_" in configs[0]["config_id"]
    assert configs[0]["config_id"].startswith("C01_threads_")


def test_build_defrag_threshold_safe_compare() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    baseline["config"]["defrag_thold"] = 0.3

    campaign = {"campaign_id": "C13_defrag", "variable": "defrag_thold", "values": [0.3]}

    configs = mod.build_config_list(baseline, campaign)

    assert configs[0]["full_config"]["defrag_thold"] == pytest.approx(0.3)
    assert "--defrag-thold" in configs[0]["server_args"]
    idx = configs[0]["server_args"].index("--defrag-thold")
    assert configs[0]["server_args"][idx + 1] == "0.3"


def test_build_defrag_threshold_negative() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C13_defrag", "variable": "defrag_thold", "values": [-1.0]}

    configs = mod.build_config_list(baseline, campaign)

    assert configs[0]["full_config"]["defrag_thold"] == -1.0
    assert "--defrag-thold" in configs[0]["server_args"]
    idx = configs[0]["server_args"].index("--defrag-thold")
    assert configs[0]["server_args"][idx + 1] == "-1"
