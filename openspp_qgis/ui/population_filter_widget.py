# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Population filter widget for spatial query dialogs.

Provides program and CEL expression filter controls that read available
options from the server's process description. The filter persists across
queries and integrates with both the stats panel and proximity dialog.
"""

from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QWidget,
)


FILTER_MODES = [
    ("and", "Both must match (AND)"),
    ("or", "Either matches (OR)"),
    ("gap", "Eligible but not enrolled (Gap)"),
]


class PopulationFilterWidget(QWidget):
    """Widget for filtering population by program and/or CEL expression."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Internal state for filter options
        self._program_labels = []
        self._program_values = []
        self._expression_labels = []
        self._expression_values = []
        self._selected_program_idx = -1
        self._selected_expression_idx = -1
        self._selected_mode = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the filter controls."""
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._filter_label = QLabel("<b>Population Filter</b>")
        layout.addRow(self._filter_label)

        self.program_combo = QComboBox()
        self.program_combo.currentIndexChanged.connect(self._on_program_changed)
        layout.addRow("Program:", self.program_combo)

        self.expression_combo = QComboBox()
        self.expression_combo.currentIndexChanged.connect(
            self._on_expression_changed
        )
        layout.addRow("Criteria:", self.expression_combo)

        self.mode_combo = QComboBox()
        for mode_value, mode_label in FILTER_MODES:
            self.mode_combo.addItem(mode_label, mode_value)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addRow("Filter mode:", self.mode_combo)

        # Mode row starts hidden
        self.mode_combo.setVisible(False)

    def populate(self, client):
        """Populate combos from server process description.

        Args:
            client: OpenSppClient instance with get_population_filter_metadata()
        """
        try:
            metadata = client.get_population_filter_metadata()
        except Exception:
            metadata = {"programs": [], "expressions": []}

        programs = metadata.get("programs", [])
        expressions = metadata.get("expressions", [])

        self._program_labels = [p["name"] for p in programs if p.get("name")]
        self._program_values = [p["id"] for p in programs if p.get("name")]
        self._expression_labels = [
            e["name"] for e in expressions if e.get("name")
        ]
        self._expression_values = [
            e["code"] for e in expressions if e.get("name")
        ]

        # Reset selection state
        self._selected_program_idx = -1
        self._selected_expression_idx = -1
        self._selected_mode = None

        # Populate program combo
        self.program_combo.clear()
        self.program_combo.addItem("All programs", None)
        for label in self._program_labels:
            self.program_combo.addItem(label, label)

        # Populate expression combo
        self.expression_combo.clear()
        self.expression_combo.addItem("No filter", None)
        for label in self._expression_labels:
            self.expression_combo.addItem(label, label)

        # Hide widget if no options available
        has_options = bool(self._program_labels) or bool(self._expression_labels)
        self.setVisible(has_options)

        self._update_mode_visibility()

    def get_filter(self):
        """Build population_filter dict from current selections.

        Returns:
            dict or None: The filter dict, or None if nothing selected.
            Omits 'mode' when only one filter is active.
        """
        has_program = self._selected_program_idx >= 0
        has_expression = self._selected_expression_idx >= 0

        if not has_program and not has_expression:
            return None

        result = {}

        if has_program and self._selected_program_idx < len(self._program_values):
            result["program"] = self._program_values[self._selected_program_idx]

        if has_expression and self._selected_expression_idx < len(
            self._expression_values
        ):
            result["cel_expression"] = self._expression_values[
                self._selected_expression_idx
            ]

        # Only include mode when both filters are active
        if has_program and has_expression and self._selected_mode:
            result["mode"] = self._selected_mode

        return result if result else None

    def describe_filter(self):
        """Return a human-readable description of the active filter.

        Returns:
            str: Description, or "" if no filter is active.
        """
        has_program = self._selected_program_idx >= 0
        has_expression = self._selected_expression_idx >= 0

        if not has_program and not has_expression:
            return ""

        program_name = ""
        if has_program and self._selected_program_idx < len(self._program_labels):
            program_name = self._program_labels[self._selected_program_idx]

        expression_name = ""
        if has_expression and self._selected_expression_idx < len(
            self._expression_labels
        ):
            expression_name = self._expression_labels[
                self._selected_expression_idx
            ]

        if has_program and has_expression:
            if self._selected_mode == "gap":
                return f"Gap: {expression_name} / {program_name}"
            elif self._selected_mode == "or":
                return f"{program_name} OR {expression_name}"
            else:
                return f"{program_name} AND {expression_name}"
        elif has_program:
            return f"Program: {program_name}"
        else:
            return f"Criteria: {expression_name}"

    def _on_program_changed(self, index):
        """Handle program combo selection change."""
        # Index 0 is "All programs" (None), real programs start at index 1
        if index <= 0:
            self._selected_program_idx = -1
        else:
            self._selected_program_idx = index - 1
        self._update_mode_visibility()

    def _on_expression_changed(self, index):
        """Handle expression combo selection change."""
        # Index 0 is "No filter" (None), real expressions start at index 1
        if index <= 0:
            self._selected_expression_idx = -1
        else:
            self._selected_expression_idx = index - 1
        self._update_mode_visibility()

    def _on_mode_changed(self, index):
        """Handle mode combo selection change."""
        if 0 <= index < len(FILTER_MODES):
            self._selected_mode = FILTER_MODES[index][0]
        else:
            self._selected_mode = None

    def _update_mode_visibility(self):
        """Show/hide mode combo based on whether both filters are active."""
        has_program = self._selected_program_idx >= 0
        has_expression = self._selected_expression_idx >= 0
        both_active = has_program and has_expression
        self.mode_combo.setVisible(both_active)

        if both_active and self._selected_mode is None:
            self._selected_mode = "and"
