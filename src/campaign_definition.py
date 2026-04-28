from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from src.config import CONFIGS_DIR

logger = logging.getLogger(__name__)

BASELINE_YAML = CONFIGS_DIR / "baseline.yaml"
CAMPAIGNS_DIR = CONFIGS_DIR / "campaigns"


class CampaignPurityViolationError(ValueError):
    """
    Raised when a campaign YAML changes more than one field from baseline.yaml.
    One campaign = one variable. This rule is enforced before any measurement
    is taken.
    """


def load_baseline(path: Path = BASELINE_YAML) -> dict[str, Any]:
    """Load and return the baseline YAML."""
    if not path.is_file():
        raise FileNotFoundError(f"baseline.yaml not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_campaign(campaign_id: str) -> dict[str, Any]:
    """Load and return the campaign YAML for the given campaign_id."""
    path = CAMPAIGNS_DIR / f"{campaign_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Campaign YAML not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_campaign_purity(
    baseline: dict[str, Any],
    campaign: dict[str, Any],
) -> str:
    """
    Verify that the campaign changes exactly one config field from baseline.
    Returns the variable name being swept.
    Raises CampaignPurityViolationError if zero or >1 fields differ.
    """
    variable = campaign.get("variable")
    if not variable or variable == "interaction" or campaign.get("auto_generated"):
        # Interaction and auto-generated campaigns bypass purity check
        return variable or "interaction"

    baseline_config: dict[str, Any] = baseline.get("config", {})
    values = campaign.get("values", [])

    if not values:
        raise CampaignPurityViolationError(
            f"Campaign {campaign['campaign_id']} has no values to sweep."
        )

    # Verify the variable exists in baseline config
    if variable not in baseline_config and variable != "cpu_affinity":
        raise CampaignPurityViolationError(
            f"Campaign variable '{variable}' is not a field in baseline.yaml config section.\n"
            f"Known config fields: {list(baseline_config.keys())}"
        )

    logger.info(
        "Campaign purity check passed: variable='%s', values=%s",
        variable,
        values,
    )
    return variable


def build_config_list(
    baseline: dict[str, Any],
    campaign: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Build the list of configs to test for this campaign.

    Each entry is a dict containing:
      - config_id: string (e.g., "C01_TB04")
      - variable_name: the field being swept
      - variable_value: the value for this config
      - full_config: merged baseline config + this value
      - server_args: list of --flag value pairs for llama-server

    C08 (interaction) is handled separately — its values must already be
    populated in the campaign YAML by score.py.
    """
    campaign_id = campaign["campaign_id"]
    variable = campaign.get("variable", "")
    values = campaign.get("values", [])
    baseline_config = baseline.get("config", {})

    configs = []
    for value in values:
        # Build a short config ID suffix
        val_str = (
            str(value)
            .replace(".", "p")
            .replace("-", "m")
            .replace(",", "")
            .replace("=", "e")[:12]
        )
        config_id = f"{campaign_id}_{val_str}"

        # Merge baseline + this value
        full_config = dict(baseline_config)
        if variable == "interaction" and isinstance(value, dict):
            # Interaction campaigns: each value is a dict of variable overrides
            config_id = value.get("config_id", f"{campaign_id}_combined")
            full_config.update(value.get("overrides", value))
        elif variable == "cpu_affinity":
            full_config["_cpu_affinity"] = value
        elif variable == "kv_cache_type_k":
            # C03: mirrors K and V
            full_config["kv_cache_type_k"] = value
            if campaign.get("kv_mirror_v", False):
                full_config["kv_cache_type_v"] = value
        else:
            full_config[variable] = value

        # Build server args from full_config
        server_args = _config_to_server_args(full_config, baseline)

        configs.append(
            {
                "config_id": config_id,
                "variable_name": variable,
                "variable_value": value,
                "full_config": full_config,
                "server_args": server_args,
                "cpu_affinity_mask": _get_affinity_mask(full_config, campaign),
            }
        )

    return configs


def _config_to_server_args(config: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """
    Convert a merged config dict to a llama-server argument list.
    Does not include --host, --port, or --model (added by server.py).
    """
    args: list[str] = []

    # Context
    if "context_size" in config:
        args += ["-c", str(config["context_size"])]

    # GPU layers (locked at 999)
    args += ["-ngl", str(config.get("n_gpu_layers", 999))]

    # Override tensor placement
    ot = config.get("override_tensor")
    if ot:
        args += ["-ot", str(ot)]

    # Flash attention: null = omit flag (server default = auto)
    fa = config.get("flash_attn")
    if fa is False:
        args += ["-fa", "0"]
    elif fa is True:
        args += ["-fa", "1"]
    # null = omit

    # Jinja templating
    if config.get("jinja", True):
        args.append("--jinja")

    # Threads — all three flags are always explicit.
    # threads_http was previously omitted when equal to its default (1), making
    # the resolved_command for C15's threads_http=1 config look identical to a
    # baseline config and hiding which parameter was being tested. (HIGH-5 fix)
    # --threads-http 1 is a no-op on the server; explicit is unambiguous.
    args += ["--threads", str(config.get("threads", 16))]
    args += ["--threads-batch", str(config.get("threads_batch", 16))]
    args += ["--threads-http", str(config.get("threads_http", 1))]

    # Batch sizes
    args += ["-ub", str(config.get("ubatch_size", 512))]
    args += ["-b", str(config.get("batch_size", 2048))]

    # Parallel slots
    n_parallel = config.get("n_parallel", 1)
    if n_parallel != 1:
        args += ["--parallel", str(n_parallel)]

    # KV cache type
    kv_k = config.get("kv_cache_type_k", "f16")
    kv_v = config.get("kv_cache_type_v", "f16")
    if kv_k != "f16":
        args += ["--cache-type-k", kv_k]
    if kv_v != "f16":
        args += ["--cache-type-v", kv_v]

    # mmap
    if not config.get("mmap", True):
        args.append("--no-mmap")

    # mlock
    if config.get("mlock", False):
        args.append("--mlock")

    # Continuous batching
    if not config.get("cont_batching", True):
        args.append("--no-cont-batching")

    # Defrag threshold
    defrag = config.get("defrag_thold", 0.1)
    if defrag != 0.1:
        if defrag < 0:
            # Negative value = disable. llama.cpp uses -1 to disable.
            args += ["--defrag-thold", "-1"]
        else:
            args += ["--defrag-thold", str(defrag)]

    return args


def _get_affinity_mask(config: dict[str, Any], campaign: dict[str, Any]) -> str | None:
    """Return CPU affinity mask string or None for OS default."""
    affinity = config.get("_cpu_affinity")
    if not affinity or affinity == "all_cores":
        return None
    # Get the P-cores-only mask from campaign details
    details = campaign.get("cpu_affinity_details", {})
    if isinstance(details, dict):
        return details.get(affinity)
    return affinity
