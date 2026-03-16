"""Tests for PopulationFilterWidget logic."""

from unittest.mock import MagicMock

from openspp_qgis.ui.population_filter_widget import PopulationFilterWidget


class TestGetFilterReturnsNone:
    """Test get_filter() default state."""

    def test_get_filter_returns_none_when_nothing_selected(self):
        """Default state with no selections returns None."""
        widget = PopulationFilterWidget()
        assert widget.get_filter() is None


class TestGetFilterProgramOnly:
    """Test get_filter() with program selection only."""

    def test_get_filter_program_only(self):
        """Returns program-only filter when only program is selected."""
        widget = PopulationFilterWidget()
        # Simulate populate() having loaded programs
        widget._program_labels = ["Cash Transfer", "Food Aid"]
        widget._program_values = [1, 5]
        widget._expression_labels = []
        widget._expression_values = []
        # Simulate selecting second program (index 1)
        widget._selected_program_idx = 1
        widget._selected_expression_idx = -1
        widget._selected_mode = None

        result = widget.get_filter()

        assert result == {"program": 5}


class TestGetFilterExpressionOnly:
    """Test get_filter() with expression selection only."""

    def test_get_filter_expression_only(self):
        """Returns expression-only filter when only expression is selected."""
        widget = PopulationFilterWidget()
        widget._program_labels = ["Cash Transfer"]
        widget._program_values = [1]
        widget._expression_labels = ["Vulnerable", "Elderly"]
        widget._expression_values = ["vuln", "elderly"]
        widget._selected_program_idx = -1
        widget._selected_expression_idx = 0
        widget._selected_mode = None

        result = widget.get_filter()

        assert result == {"cel_expression": "vuln"}


class TestGetFilterBothWithAndMode:
    """Test get_filter() with both program and expression in AND mode."""

    def test_get_filter_both_with_and_mode(self):
        """Returns combined filter with AND mode."""
        widget = PopulationFilterWidget()
        widget._program_labels = ["Cash Transfer", "Food Aid"]
        widget._program_values = [1, 5]
        widget._expression_labels = ["Vulnerable"]
        widget._expression_values = ["vuln"]
        widget._selected_program_idx = 1
        widget._selected_expression_idx = 0
        widget._selected_mode = "and"

        result = widget.get_filter()

        assert result == {
            "program": 5,
            "cel_expression": "vuln",
            "mode": "and",
        }


class TestGetFilterGapMode:
    """Test get_filter() with gap mode."""

    def test_get_filter_gap_mode(self):
        """Returns combined filter with gap mode."""
        widget = PopulationFilterWidget()
        widget._program_labels = ["Cash Transfer", "Food Aid"]
        widget._program_values = [1, 5]
        widget._expression_labels = ["Vulnerable"]
        widget._expression_values = ["vuln"]
        widget._selected_program_idx = 1
        widget._selected_expression_idx = 0
        widget._selected_mode = "gap"

        result = widget.get_filter()

        assert result == {
            "program": 5,
            "cel_expression": "vuln",
            "mode": "gap",
        }


class TestDescribeFilter:
    """Test describe_filter() human-readable descriptions."""

    def test_describe_filter_empty(self):
        """Returns empty string when nothing selected."""
        widget = PopulationFilterWidget()
        assert widget.describe_filter() == ""

    def test_describe_filter_program_only(self):
        """Returns program name when only program selected."""
        widget = PopulationFilterWidget()
        widget._program_labels = ["Cash Transfer", "Food Aid"]
        widget._program_values = [1, 5]
        widget._expression_labels = []
        widget._expression_values = []
        widget._selected_program_idx = 0
        widget._selected_expression_idx = -1
        widget._selected_mode = None

        desc = widget.describe_filter()

        assert "Cash Transfer" in desc

    def test_describe_filter_gap_mode(self):
        """Returns gap description when gap mode selected."""
        widget = PopulationFilterWidget()
        widget._program_labels = ["Cash Transfer"]
        widget._program_values = [1]
        widget._expression_labels = ["Vulnerable"]
        widget._expression_values = ["vuln"]
        widget._selected_program_idx = 0
        widget._selected_expression_idx = 0
        widget._selected_mode = "gap"

        desc = widget.describe_filter()

        # Should mention gap or both filter names
        assert "gap" in desc.lower() or "Gap" in desc


class TestPopulateHidesWhenNoOptions:
    """Test populate() hides widget when no options available."""

    def test_populate_hides_when_no_options(self):
        """Widget is hidden when both program and expression lists are empty."""
        client = MagicMock()
        client.get_population_filter_metadata.return_value = {
            "programs": [],
            "expressions": [],
        }

        widget = PopulationFilterWidget()
        widget.setVisible = MagicMock()
        widget.populate(client)

        # When no options, the widget should be hidden
        widget.setVisible.assert_called_with(False)


class TestPopulateWithOptions:
    """Test populate() stores options from client."""

    def test_populate_stores_program_options(self):
        """populate() stores program labels and values from client metadata."""
        client = MagicMock()
        client.get_population_filter_metadata.return_value = {
            "programs": [
                {"id": 1, "name": "Cash Transfer"},
                {"id": 2, "name": "Food Aid"},
            ],
            "expressions": [
                {"code": "vuln", "name": "Vulnerable", "applies_to": "individual"},
            ],
        }

        widget = PopulationFilterWidget()
        widget.setVisible = MagicMock()
        widget.populate(client)

        assert widget._program_labels == ["Cash Transfer", "Food Aid"]
        assert widget._program_values == [1, 2]
        assert widget._expression_labels == ["Vulnerable"]
        assert widget._expression_values == ["vuln"]
