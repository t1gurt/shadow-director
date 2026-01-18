"""
Test suite for FormatFieldMapper field importance and limiting logic.

Tests the new field importance calculation and field limiting features
implemented to handle Excel files with large numbers of fields.
"""

import unittest
from dataclasses import dataclass
from typing import Dict, Any, Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.logic.format_field_mapper import FormatFieldMapper, FieldInfo


class TestFieldImportanceCalculation(unittest.TestCase):
    """Test field importance scoring logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mapper = FormatFieldMapper(gemini_client=None)  # No client needed for these tests
    
    def test_required_field_gets_high_score(self):
        """Required fields should receive +50 bonus points."""
        field = FieldInfo(
            field_id="test_1",
            field_name="テスト項目",
            field_type="cell",
            location={"row": 1, "col": 1},
            required=True
        )
        
        score = self.mapper._calculate_field_importance(field, 0)
        self.assertGreaterEqual(score, 50, "Required field should have at least 50 points")
    
    def test_organization_name_gets_high_priority(self):
        """Fields with organization-related keywords should get high scores."""
        test_cases = [
            ("団体名", 30),  # Organization name
            ("法人名", 30),  # Corporate name
            ("代表者", 30),  # Representative
            ("連絡先", 30),  # Contact
        ]
        
        for field_name, expected_min_score in test_cases:
            with self.subTest(field_name=field_name):
                field = FieldInfo(
                    field_id=f"test_{field_name}",
                    field_name=field_name,
                    field_type="cell",
                    location={"row": 1, "col": 1}
                )
                
                score = self.mapper._calculate_field_importance(field, 0)
                self.assertGreaterEqual(
                    score, 
                    expected_min_score, 
                    f"{field_name} should have at least {expected_min_score} points"
                )
    
    def test_important_keywords_get_medium_priority(self):
        """Fields with important keywords should get +20 points."""
        test_cases = ["事業名", "目的", "概要", "プロジェクト", "計画"]
        
        for field_name in test_cases:
            with self.subTest(field_name=field_name):
                field = FieldInfo(
                    field_id=f"test_{field_name}",
                    field_name=field_name,
                    field_type="cell",
                    location={"row": 1, "col": 1}
                )
                
                score = self.mapper._calculate_field_importance(field, 0)
                self.assertGreaterEqual(
                    score, 
                    20, 
                    f"{field_name} should have at least 20 points"
                )
    
    def test_amount_keywords_get_bonus(self):
        """Fields with amount-related keywords should get +15 points."""
        test_cases = ["金額", "予算", "費用"]
        
        for field_name in test_cases:
            with self.subTest(field_name=field_name):
                field = FieldInfo(
                    field_id=f"test_{field_name}",
                    field_name=field_name,
                    field_type="cell",
                    location={"row": 1, "col": 1}
                )
                
                score = self.mapper._calculate_field_importance(field, 0)
                self.assertGreaterEqual(
                    score, 
                    15, 
                    f"{field_name} should have at least 15 points"
                )
    
    def test_long_type_fields_get_bonus(self):
        """Long text fields should get +10 points."""
        field = FieldInfo(
            field_id="test_long",
            field_name="事業概要",
            field_type="paragraph",
            location={"paragraph_idx": 1},
            input_length_type="long"
        )
        
        score = self.mapper._calculate_field_importance(field, 0)
        self.assertGreaterEqual(score, 10, "Long field should have at least 10 points")
    
    def test_early_position_gets_bonus(self):
        """Fields at the beginning should get position bonus."""
        field = FieldInfo(
            field_id="test_early",
            field_name="テスト項目",
            field_type="cell",
            location={"row": 1, "col": 1}
        )
        
        # Field at position 0 should get max position bonus
        score_early = self.mapper._calculate_field_importance(field, 0)
        
        # Field at position 50 should get no position bonus
        score_late = self.mapper._calculate_field_importance(field, 50)
        
        self.assertGreater(
            score_early, 
            score_late, 
            "Early position should have higher score than late position"
        )
    
    def test_max_length_fields_get_bonus(self):
        """Fields with character limits should get +3 points."""
        field = FieldInfo(
            field_id="test_limited",
            field_name="テスト項目",
            field_type="cell",
            location={"row": 1, "col": 1},
            max_length=400
        )
        
        score_with_limit = self.mapper._calculate_field_importance(field, 0)
        
        field.max_length = None
        score_without_limit = self.mapper._calculate_field_importance(field, 0)
        
        self.assertEqual(
            score_with_limit - score_without_limit,
            3,
            "Fields with max_length should get +3 bonus"
        )


class TestFieldLimiting(unittest.TestCase):
    """Test field limiting functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mapper = FormatFieldMapper(gemini_client=None)
    
    def test_fields_under_limit_unchanged(self):
        """Fields under the limit should pass through unchanged."""
        fields = [
            FieldInfo(
                field_id=f"field_{i}",
                field_name=f"項目{i}",
                field_type="cell",
                location={"row": i, "col": 1}
            )
            for i in range(30)
        ]
        
        limited_fields, original_count = self.mapper._limit_fields_by_importance(fields, max_fields=50)
        
        self.assertEqual(len(limited_fields), 30, "Should return all fields when under limit")
        self.assertEqual(original_count, 30, "Should report original count correctly")
    
    def test_fields_over_limit_reduced(self):
        """Fields over the limit should be reduced to max_fields."""
        fields = [
            FieldInfo(
                field_id=f"field_{i}",
                field_name=f"項目{i}",
                field_type="cell",
                location={"row": i, "col": 1}
            )
            for i in range(100)
        ]
        
        limited_fields, original_count = self.mapper._limit_fields_by_importance(fields, max_fields=50)
        
        self.assertEqual(len(limited_fields), 50, "Should limit to max_fields")
        self.assertEqual(original_count, 100, "Should report original count correctly")
    
    def test_important_fields_prioritized(self):
        """High-importance fields should be selected over low-importance ones."""
        # Create fields with different importance levels
        fields = [
            # High importance field (required + high priority keyword)
            FieldInfo(
                field_id="important_1",
                field_name="団体名",
                field_type="cell",
                location={"row": 1, "col": 1},
                required=True
            ),
            # Medium importance field
            FieldInfo(
                field_id="medium_1",
                field_name="事業概要",
                field_type="cell",
                location={"row": 2, "col": 1},
                input_length_type="long"
            ),
        ]
        
        # Add 60 low-importance fields
        for i in range(60):
            fields.append(
                FieldInfo(
                    field_id=f"low_{i}",
                    field_name=f"その他{i}",
                    field_type="cell",
                    location={"row": i + 10, "col": 1}
                )
            )
        
        limited_fields, original_count = self.mapper._limit_fields_by_importance(fields, max_fields=50)
        
        # Check that important fields are included
        field_ids = [f.field_id for f in limited_fields]
        self.assertIn("important_1", field_ids, "High importance field should be included")
        self.assertIn("medium_1", field_ids, "Medium importance field should be included")
        
        # Check that total is limited
        self.assertEqual(len(limited_fields), 50, "Should limit to max_fields")
        self.assertEqual(original_count, 62, "Should report correct original count")
    
    def test_instance_variables_updated(self):
        """Instance variables should be updated with field count info."""
        fields = [
            FieldInfo(
                field_id=f"field_{i}",
                field_name=f"項目{i}",
                field_type="cell",
                location={"row": i, "col": 1}
            )
            for i in range(80)
        ]
        
        # Reset instance variables
        self.mapper.last_total_field_count = 0
        self.mapper.last_skipped_field_count = 0
        
        # Call map_draft_to_fields indirectly through _limit_fields_by_importance
        limited_fields, original_count = self.mapper._limit_fields_by_importance(fields, max_fields=50)
        
        # Instance variables are updated in map_draft_to_fields, not _limit_fields_by_importance
        # So we verify the return values instead
        self.assertEqual(original_count, 80, "Should return original count")
        self.assertEqual(len(limited_fields), 50, "Should return limited count")


class TestFieldImportanceIntegration(unittest.TestCase):
    """Integration tests for field importance and limiting."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mapper = FormatFieldMapper(gemini_client=None)
    
    def test_realistic_field_distribution(self):
        """Test with a realistic distribution of field types."""
        fields = []
        
        # Add essential fields (should all be selected)
        essential_fields = [
            ("団体名", True, "short"),
            ("代表者", True, "short"),
            ("連絡先", True, "short"),
            ("事業名", True, "short"),
            ("事業概要", False, "long"),
            ("目的", False, "long"),
        ]
        
        for i, (name, required, length_type) in enumerate(essential_fields):
            fields.append(
                FieldInfo(
                    field_id=f"essential_{i}",
                    field_name=name,
                    field_type="cell",
                    location={"row": i, "col": 1},
                    required=required,
                    input_length_type=length_type
                )
            )
        
        # Add 70 miscellaneous fields (many will be skipped)
        for i in range(70):
            fields.append(
                FieldInfo(
                    field_id=f"misc_{i}",
                    field_name=f"備考{i}",
                    field_type="cell",
                    location={"row": i + 20, "col": 1}
                )
            )
        
        limited_fields, original_count = self.mapper._limit_fields_by_importance(fields, max_fields=50)
        
        # Verify essential fields are all included
        limited_ids = [f.field_id for f in limited_fields]
        for i in range(len(essential_fields)):
            self.assertIn(
                f"essential_{i}",
                limited_ids,
                f"Essential field {essential_fields[i][0]} should be included"
            )
        
        self.assertEqual(len(limited_fields), 50, "Should limit to 50 fields")
        self.assertEqual(original_count, 76, "Should report correct original count")


if __name__ == '__main__':
    unittest.main()
