"""Universal log & event source connectors package."""
from services.connectors.registry import (
    CONNECTOR_REGISTRY,
    get_connector_spec,
    list_connector_specs,
    mask_source_config,
    merge_secret_fields,
    validate_source_config,
)
from services.connectors.parser import (
    apply_transforms,
    extract_fields,
    parse_raw_payload,
)
from services.connectors.simulator import (
    SIMULATOR_PRESETS,
    generate_simulated_event,
    list_simulator_presets,
)
from services.connectors.dry_run import dry_run_against_rules
from services.connectors.ingest_manager import ingest_manager, ingest_records

__all__ = [
    "CONNECTOR_REGISTRY",
    "get_connector_spec",
    "list_connector_specs",
    "mask_source_config",
    "merge_secret_fields",
    "validate_source_config",
    "apply_transforms",
    "extract_fields",
    "parse_raw_payload",
    "SIMULATOR_PRESETS",
    "generate_simulated_event",
    "list_simulator_presets",
    "dry_run_against_rules",
    "ingest_manager",
    "ingest_records",
]
