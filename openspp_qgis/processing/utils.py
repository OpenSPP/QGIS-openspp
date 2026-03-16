# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Shared utilities for OpenSPP Processing algorithms."""

import logging
import re

logger = logging.getLogger(__name__)


def fetch_variable_options(client, cached_names=None):
    """Fetch variable names from the server for Processing enum dropdowns.

    Uses the published statistics endpoint to discover available variables.
    Returns the cached list if already populated, or an empty list if the
    client is unavailable.

    Args:
        client: OpenSppClient instance (or None)
        cached_names: Previously fetched variable names (returned as-is if non-empty)

    Returns:
        List of variable name strings
    """
    if cached_names:
        return cached_names

    if not client:
        return []

    try:
        stats = client.get_published_statistics()
        names = []
        for category in stats.get("categories", []):
            for stat in category.get("statistics", []):
                name = stat.get("name", "")
                if name:
                    names.append(name)
        return names
    except Exception:
        logger.warning("Failed to fetch variable options", exc_info=True)
        return []


def fetch_dimension_options(client, cached_names=None):
    """Fetch dimension names from the server for Processing enum dropdowns.

    Uses the process description's x-openspp-dimensions extension to
    discover available disaggregation dimensions.

    Args:
        client: OpenSppClient instance (or None)
        cached_names: Previously fetched dimension names (returned as-is if non-empty)

    Returns:
        List of dimension name strings
    """
    if cached_names:
        return cached_names

    if not client:
        return []

    try:
        dimensions = client.get_dimensions_from_process()
        return [d["name"] for d in dimensions if d.get("name")]
    except Exception:
        logger.warning("Failed to fetch dimension options", exc_info=True)
        return []


def sanitize_breakdown_field_name(labels):
    """Build a QGIS-safe field name from a breakdown cell's labels dict.

    Sorting by dimension name ensures stable column ordering regardless
    of dict iteration order.

    Args:
        labels: Dict of {dim_name: {"value": ..., "display": ...}}

    Returns:
        Sanitized field name like "disagg_Female_Child_017"
    """
    parts = [labels[dim]["display"] for dim in sorted(labels)]
    raw = "disagg_" + "_".join(parts)
    return re.sub(r"[^a-zA-Z0-9_]", "", raw.replace(" ", "_"))
