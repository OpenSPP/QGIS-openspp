# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Shared authentication utilities for OpenSPP QGIS plugin.

Manages the APIHeader auth config that injects a Bearer token into
OAPIF connection requests. Used by both the connection dialog (initial
setup) and the token refresh timer (periodic updates).
"""

import logging
import uuid

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsSettings

logger = logging.getLogger(__name__)


def update_oapif_auth_token(bearer_token, connection_name=None):
    """Create or update the APIHeader auth config for OAPIF connections.

    Uses QGIS's APIHeader auth method to inject a pre-acquired Bearer
    token into HTTP request headers. If a config already exists (stored
    in openspp/oapif_auth_config_id), it is updated in place. Otherwise
    a new config is created.

    Args:
        bearer_token: JWT Bearer token string
        connection_name: Connection name for new config display name.
            Only used when creating a new config.

    Returns:
        Auth config ID string, or None if creation/update failed
    """
    try:
        from qgis.core import QgsAuthMethodConfig

        auth_manager = QgsApplication.authManager()
        settings = QgsSettings()

        header_map = {"Authorization": f"Bearer {bearer_token}"}

        # Update existing config if present
        existing_id = settings.value("openspp/oapif_auth_config_id", "")
        if existing_id:
            config = QgsAuthMethodConfig()
            if auth_manager.loadAuthenticationConfig(
                existing_id, config, True
            ):
                if config.method() == "APIHeader":
                    config.setConfigMap(header_map)
                    auth_manager.updateAuthenticationConfig(config)
                    QgsMessageLog.logMessage(
                        f"Updated APIHeader auth config "
                        f"'{existing_id}'",
                        "OpenSPP",
                        Qgis.Info,
                    )
                    return existing_id

                # Method is wrong (e.g. "OAuth2" from earlier attempt).
                # The method is immutable after creation in QGIS's
                # auth DB, so we must delete and recreate.
                QgsMessageLog.logMessage(
                    f"Replacing auth config '{existing_id}' "
                    f"(method '{config.method()}' -> 'APIHeader')",
                    "OpenSPP",
                    Qgis.Info,
                )
                auth_manager.removeAuthenticationConfig(existing_id)
                settings.remove("openspp/oapif_auth_config_id")

        # Create new APIHeader auth config
        config = QgsAuthMethodConfig("APIHeader")
        display_name = connection_name or "OpenSPP"
        config.setName(f"OpenSPP Token - {display_name}")
        config.setConfigMap(header_map)
        config.setId(uuid.uuid4().hex[:7])

        if auth_manager.storeAuthenticationConfig(config):
            config_id = config.id()
            settings.setValue(
                "openspp/oapif_auth_config_id", config_id
            )
            QgsMessageLog.logMessage(
                f"Created APIHeader auth config "
                f"'{config_id}' for OAPIF",
                "OpenSPP",
                Qgis.Info,
            )
            return config_id

        QgsMessageLog.logMessage(
            "Failed to store APIHeader auth config "
            "in QGIS auth manager",
            "OpenSPP",
            Qgis.Warning,
        )
        return None
    except Exception as e:
        QgsMessageLog.logMessage(
            f"Failed to create/update APIHeader auth config: {e}",
            "OpenSPP",
            Qgis.Warning,
        )
        return None
