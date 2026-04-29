from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from src.config import CONFIGS_DIR

logger = logging.getLogger(__name__)

BASELINE_YAML = CONFIGS_DIR / "baseline.yaml"
CAMPAIGNS_DIR = CONFIGS_DIR / "campaigns"

KNOWN_CONFIG_FIELDS = frozenset({
    "host",
    "n_gpu_layers",
    "override_tensor",
    "flash_attn",
    "jinja",
    "context_size",
    "threads",
    "threads_batch",
    "threads_http",
    "ubatch_size",
    "batch_size",
    "n_parallel",
    "kv_cache_type_k",
    "kv_cache_type_v",
    "mmap",
    "mlock",
    "cont_batching",
    "defrag_thold",
    "_cpu_affinity",
})

BASELINE_CONFIG_FIELDS = frozenset(KNOWN_CONFIG_FIELDS - {"_cpu_affinity"})


class CampaignPurityViolationError(ValueError):
    """
    Raised when a campaign YAML changes more than one field from baseline.yaml.
    One campaign = one variable. This rule is enforced before any measurement
    is taken.
    """


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    """Load a YAML file and verify it contains a mapping (dict)."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise CampaignPurityViolationError(
            f"{label} is not a mapping (got {type(data).__name__!r}): {path}"
        )
    return data


def load_baseline(path: Path = BASELINE_YAML) -> dict[str, Any]:
    """Load and return the baseline YAML."""
    return _load_yaml_mapping(path, "baseline.yaml")


def load_campaign(campaign_id: str) -> dict[str, Any]:
    """Load and return the campaign YAML for the given campaign_id."""
    path = CAMPAIGNS_DIR / f"{campaign_id}.yaml"
    return _load_yaml_mapping(path, "Campaign YAML")


def _cid(campaign_id: str) -> str:
    """Return campaign_id or '?' for error messages."""
    return campaign_id if campaign_id else "?"


def _is_non_empty_str(value: object) -> bool:
    """Return True if value is a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def _is_valid_variable(variable: str) -> bool:
    """Return True if variable is a known config field or special field."""
    return variable in KNOWN_CONFIG_FIELDS or variable in ("cpu_affinity", "interaction")


def _validate_config_keys(config: dict[str, Any]) -> None:
    """Raise CampaignPurityViolationError if config contains unknown keys."""
    unknown = [k for k in config if k not in BASELINE_CONFIG_FIELDS]
    if unknown:
        raise CampaignPurityViolationError(
            f"Baseline config contains invalid key(s): {unknown}. "
            f"Allowed keys are: {sorted(BASELINE_CONFIG_FIELDS)}"
        )


def validate_campaign_purity(
    baseline: dict[str, Any],
    campaign: dict[str, Any],
) -> str:
    """
    Verify that the campaign changes exactly one config field from baseline.
    Returns the variable name being swept.
    Raises CampaignPurityViolationError if zero or >1 fields differ.
    """
    campaign_id = _cid(campaign.get("campaign_id", ""))

    variable_raw = campaign.get("variable")
    if not _is_non_empty_str(variable_raw):
        raise CampaignPurityViolationError(
            f"Campaign {campaign_id} has no variable (got {variable_raw!r})"
        )
    variable = variable_raw.strip()

    values = campaign.get("values")
    if not values or not isinstance(values, list):
        raise CampaignPurityViolationError(
            f"Campaign {campaign_id} has no values to sweep (got {values!r})"
        )

    if variable == "interaction":
        logger.info(
            "Interaction campaign purity check passed: variable='%s', values=%s",
            variable,
            values,
        )
        return variable

    _raw_config = baseline.get("config")
    if not isinstance(_raw_config, dict):
        raise CampaignPurityViolationError(
            f"Baseline config is not a dict (got {type(_raw_config).__name__})"
        )
    baseline_config: dict[str, Any] = _raw_config
    _validate_config_keys(baseline_config)

    if not _is_valid_variable(variable):
        raise CampaignPurityViolationError(
            f"Campaign variable '{variable}' is not a known config field.\n"
            f"Known config fields: {sorted(list(KNOWN_CONFIG_FIELDS) + ['cpu_affinity', 'interaction'])}"
        )

    logger.info(
        "Campaign purity check passed: variable='%s', values=%s",
        variable,
        values,
    )
    return variable


def _make_config_id(campaign_id: str, value: object) -> str:
    """Build a deterministic, collision-resistant config_id with an 8-char SHA256 digest suffix."""
    if isinstance(value, (dict, list, tuple)):
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    else:
        raw = str(value)

    cleaned = (
        raw.replace(".", "p")
        .replace("-", "m")
        .replace(",", "")
        .replace("=", "e")
        .replace('"', "")
        .replace("{", "")
        .replace("}", "")
        .replace("[", "")
        .replace("]", "")
        .replace(":", "")
        .replace(" ", "")
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()[:8]
    prefix = cleaned[:24] if len(cleaned) > 24 else cleaned
    return f"{campaign_id}_{prefix}_{digest}"


def _normalize_campaign_inputs(
    campaign: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[str, str, list, dict[str, Any]]:
    """Validate and return campaign_id, variable, values, baseline_config."""
    _campaign_id = campaign.get("campaign_id")
    if not _is_non_empty_str(_campaign_id):
        raise CampaignPurityViolationError(
            f"Campaign has no valid campaign_id (got {_campaign_id!r})"
        )
    campaign_id = _campaign_id.strip()

    _var_raw = campaign.get("variable")
    if not _is_non_empty_str(_var_raw):
        raise CampaignPurityViolationError(
            f"Campaign {campaign_id} has no variable (got {_var_raw!r})"
        )
    variable = _var_raw.strip()

    values = campaign.get("values")
    if not values or not isinstance(values, list):
        raise CampaignPurityViolationError(
            f"Campaign {campaign_id} has no values to sweep (got {values!r})"
        )

    _raw_config = baseline.get("config")
    if not isinstance(_raw_config, dict):
        raise CampaignPurityViolationError(
            f"Baseline config is not a dict (got {type(_raw_config).__name__})"
        )

    _validate_config_keys(_raw_config)

    if not _is_valid_variable(variable):
        raise CampaignPurityViolationError(
            f"Campaign {campaign_id} variable '{variable}' is not a known config field.\n"
            f"Known config fields: {sorted(list(KNOWN_CONFIG_FIELDS) + ['cpu_affinity', 'interaction'])}"
        )

    return campaign_id, variable, values, _raw_config


def _expand_interaction_value(campaign_id: str, value: object) -> tuple[dict[str, Any], str | None]:
    if not isinstance(value, dict):
        raise CampaignPurityViolationError(
            f"Campaign {campaign_id} interaction value must be a dict, "
            f"got {type(value).__name__}"
        )
    config_id = None
    raw_cfg_id = value.get("config_id")
    if raw_cfg_id is not None:
        if not isinstance(raw_cfg_id, str):
            raise CampaignPurityViolationError(
                f"Campaign {campaign_id} interaction config_id must be a string, "
                f"got {type(raw_cfg_id).__name__}"
            )
        if not raw_cfg_id.strip():
            raise CampaignPurityViolationError(
                f"Campaign {campaign_id} interaction config_id must not be blank"
            )
        config_id = raw_cfg_id.strip()
    if "overrides" in value:
        overrides = value["overrides"]
    else:
        overrides = {k: v for k, v in value.items() if k != "config_id"}
    if not isinstance(overrides, dict):
        raise CampaignPurityViolationError(
            f"Campaign {campaign_id} interaction overrides must be a dict, "
            f"got {type(overrides).__name__}"
        )
    return overrides, config_id


def _apply_interaction_config(
    full_config: dict[str, Any],
    campaign_id: str,
    value: object,
    default_config_id: str,
) -> str:
    """Apply interaction overrides and resolve config_id."""
    overrides, override_config_id = _expand_interaction_value(campaign_id, value)
    full_config.update(overrides)
    return override_config_id or default_config_id


def _apply_kv_cache_config(
    full_config: dict[str, Any],
    value: object,
    kv_mirror_v: bool,
) -> None:
    """Apply kv_cache_type_k (and optionally kv_cache_type_v) to full_config."""
    full_config["kv_cache_type_k"] = value
    if kv_mirror_v:
        full_config["kv_cache_type_v"] = value


def _expand_value(
    baseline_config: dict[str, Any],
    variable: str,
    campaign_id: str,
    kv_mirror_v: bool,
    value: object,
) -> tuple[dict[str, Any], str]:
    """Build full_config and resolve config_id for a single sweep value."""
    config_id = _make_config_id(campaign_id, value)
    full_config = dict(baseline_config)

    if variable == "interaction":
        config_id = _apply_interaction_config(full_config, campaign_id, value, config_id)
    elif variable == "cpu_affinity":
        full_config["_cpu_affinity"] = value
    elif variable == "kv_cache_type_k":
        _apply_kv_cache_config(full_config, value, kv_mirror_v)
    else:
        full_config[variable] = value

    return full_config, config_id


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
    campaign_id, variable, values, baseline_config = _normalize_campaign_inputs(
        campaign, baseline
    )

    configs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    kv_mirror_v = campaign.get("kv_mirror_v", False)
    for value in values:
        full_config, config_id = _expand_value(
            baseline_config, variable, campaign_id, kv_mirror_v, value
        )

        unknown_keys = [k for k in full_config if k not in KNOWN_CONFIG_FIELDS]
        if unknown_keys:
            raise CampaignPurityViolationError(
                f"Campaign {campaign_id} config expansion produced invalid key(s): {unknown_keys}. "
                f"Check interaction overrides or baseline config. "
                f"Allowed keys are: {sorted(KNOWN_CONFIG_FIELDS)}"
            )

        if config_id in seen_ids:
            raise CampaignPurityViolationError(
                f"Campaign {campaign_id} produced duplicate config_id: {config_id!r}"
            )
        seen_ids.add(config_id)

        configs.append(
            {
                "config_id": config_id,
                "variable_name": variable,
                "variable_value": value,
                "full_config": full_config,
                "server_args": _config_to_server_args(full_config),
                "cpu_affinity_mask": _get_affinity_mask(full_config, campaign),
            }
        )

    return configs


def _config_to_server_args(config: dict[str, Any]) -> list[str]:
    """
    Convert a merged config dict to a llama-server argument list.
    Does not include --host, --port, or --model (added by server.py).
    """
    args: list[str] = []

    if "context_size" in config:
        args += ["-c", str(config["context_size"])]

    args += ["-ngl", str(config.get("n_gpu_layers", 999))]

    ot = config.get("override_tensor")
    if ot:
        args += ["-ot", str(ot)]

    fa = config.get("flash_attn")
    if fa is False:
        args += ["-fa", "0"]
    elif fa is True:
        args += ["-fa", "1"]

    if config.get("jinja", True):
        args.append("--jinja")

    args += ["--threads", str(config.get("threads", 16))]
    args += ["--threads-batch", str(config.get("threads_batch", 16))]
    args += ["--threads-http", str(config.get("threads_http", 1))]

    args += ["-ub", str(config.get("ubatch_size", 512))]
    args += ["-b", str(config.get("batch_size", 2048))]

    n_parallel = config.get("n_parallel", 1)
    if n_parallel != 1:
        args += ["--parallel", str(n_parallel)]

    _apply_cache_type_flags(config, args)
    _apply_bool_flags(config, args)

    defrag = config.get("defrag_thold", 0.1)
    if abs(defrag - 0.1) > 1e-9:
        if defrag < 0:
            args += ["--defrag-thold", "-1"]
        else:
            args += ["--defrag-thold", str(defrag)]

    return args


def _apply_cache_type_flags(config: dict[str, Any], args: list[str]) -> None:
    kv_k = config.get("kv_cache_type_k", "f16")
    kv_v = config.get("kv_cache_type_v", "f16")
    if kv_k != "f16":
        args.extend(["--cache-type-k", str(kv_k)])
    if kv_v != "f16":
        args.extend(["--cache-type-v", str(kv_v)])


def _apply_bool_flags(config: dict[str, Any], args: list[str]) -> None:
    if not config.get("mmap", True):
        args.append("--no-mmap")
    if config.get("mlock", False):
        args.append("--mlock")
    if not config.get("cont_batching", True):
        args.append("--no-cont-batching")


def _get_affinity_mask(config: dict[str, Any], campaign: dict[str, Any]) -> str | None:
    """Return CPU affinity mask string or None for OS default."""
    affinity = config.get("_cpu_affinity")
    if not affinity or affinity == "all_cores":
        return None

    details = campaign.get("cpu_affinity_details")
    if not isinstance(details, dict):
        raise CampaignPurityViolationError(
            f"Campaign {_cid(campaign.get('campaign_id', ''))} "
            f"requests affinity '{affinity}' but cpu_affinity_details is missing or not a dict"
        )

    mask = details.get(affinity)
    if mask is None:
        raise CampaignPurityViolationError(
            f"Campaign {_cid(campaign.get('campaign_id', ''))} "
            f"has no affinity mask for key '{affinity}'. Available: {list(details.keys())}"
        )
    if not isinstance(mask, str) or not mask.strip():
        raise CampaignPurityViolationError(
            f"Campaign {_cid(campaign.get('campaign_id', ''))} "
            f"affinity mask for key '{affinity}' must be a non-empty string, "
            f"got {type(mask).__name__!r}: {mask!r}"
        )
    return mask.strip()
