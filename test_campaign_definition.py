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
        raise  # dead code, suppresses CodeQL mixed-return warning


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


def test_validate_campaign_purity_standard_valid_campaign() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "threads", "values": [8, 16]}

    variable = mod.validate_campaign_purity(baseline, campaign)

    assert variable == "threads"


def test_validate_campaign_purity_missing_values() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "threads", "values": []}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no values to sweep"):
        mod.validate_campaign_purity(baseline, campaign)


def test_validate_campaign_purity_unknown_variable() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C99_unknown", "variable": "unknown_flag", "values": [1]}

    with pytest.raises(mod.CampaignPurityViolationError, match="is not a field in baseline.yaml config section"):
        mod.validate_campaign_purity(baseline, campaign)


def test_validate_campaign_purity_interaction_bypass() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C08_interaction", "variable": "interaction", "values": []}

    variable = mod.validate_campaign_purity(baseline, campaign)

    assert variable == "interaction"


def test_validate_campaign_purity_auto_generated_bypass() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "AUTO_01", "variable": "threads", "values": [], "auto_generated": True}

    variable = mod.validate_campaign_purity(baseline, campaign)

    assert variable == "threads"


def test_validate_campaign_purity_missing_variable_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "values": [8, 16]}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no variable"):
        mod.validate_campaign_purity(baseline, campaign)


def test_validate_campaign_purity_empty_variable_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "", "values": [8, 16]}

    with pytest.raises(mod.CampaignPurityViolationError, match="has no variable"):
        mod.validate_campaign_purity(baseline, campaign)


def test_validate_campaign_purity_auto_generated_without_variable_raises() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "FINALIST", "values": [], "auto_generated": True}

    with pytest.raises(mod.CampaignPurityViolationError, match="auto_generated but has no variable"):
        mod.validate_campaign_purity(baseline, campaign)


def test_build_config_list_normal_scalar_sweep_preserves_shape() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {"campaign_id": "C01_threads", "variable": "threads", "values": [32]}

    configs = mod.build_config_list(baseline, campaign)

    assert configs == [
        {
            "config_id": "C01_threads_32",
            "variable_name": "threads",
            "variable_value": 32,
            "full_config": {
                "context_size": 4096,
                "n_gpu_layers": 999,
                "flash_attn": True,
                "jinja": True,
                "threads": 32,
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
            "server_args": [
                "-c",
                "4096",
                "-ngl",
                "999",
                "-fa",
                "1",
                "--jinja",
                "--threads",
                "32",
                "--threads-batch",
                "16",
                "--threads-http",
                "1",
                "-ub",
                "512",
                "-b",
                "2048",
            ],
            "cpu_affinity_mask": None,
        }
    ]


def test_build_config_list_interaction_override_generation() -> None:
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
    assert configs[0]["server_args"] == [
        "-c",
        "4096",
        "-ngl",
        "999",
        "-fa",
        "1",
        "--jinja",
        "--threads",
        "24",
        "--threads-batch",
        "16",
        "--threads-http",
        "1",
        "-ub",
        "512",
        "-b",
        "2048",
        "--parallel",
        "2",
    ]


def test_build_config_list_cpu_affinity_mask_behavior() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "C17_affinity",
        "variable": "cpu_affinity",
        "values": ["p_cores_only", "all_cores"],
        "cpu_affinity_details": {"p_cores_only": "0x00FF"},
    }

    configs = mod.build_config_list(baseline, campaign)

    assert configs[0]["config_id"] == "C17_affinity_p_cores_only"
    assert configs[0]["full_config"]["_cpu_affinity"] == "p_cores_only"
    assert configs[0]["cpu_affinity_mask"] == "0x00FF"
    assert configs[1]["config_id"] == "C17_affinity_all_cores"
    assert configs[1]["cpu_affinity_mask"] is None


def test_build_config_list_kv_cache_type_k_mirror_v_behavior() -> None:
    mod = _campaign_definition_module()
    baseline = _baseline()
    campaign = {
        "campaign_id": "C03_kv_cache_type_k",
        "variable": "kv_cache_type_k",
        "values": ["q8_0"],
        "kv_mirror_v": True,
    }

    configs = mod.build_config_list(baseline, campaign)

    assert configs == [
        {
            "config_id": "C03_kv_cache_type_k_q8_0",
            "variable_name": "kv_cache_type_k",
            "variable_value": "q8_0",
            "full_config": {
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
                "kv_cache_type_k": "q8_0",
                "kv_cache_type_v": "q8_0",
            },
            "server_args": [
                "-c",
                "4096",
                "-ngl",
                "999",
                "-fa",
                "1",
                "--jinja",
                "--threads",
                "16",
                "--threads-batch",
                "16",
                "--threads-http",
                "1",
                "-ub",
                "512",
                "-b",
                "2048",
                "--cache-type-k",
                "q8_0",
                "--cache-type-v",
                "q8_0",
            ],
            "cpu_affinity_mask": None,
        }
    ]
