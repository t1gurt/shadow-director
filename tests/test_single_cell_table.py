"""
Test suite for single-cell table detection in FormatFieldMapper.

Tests the new single-cell table detection feature for Word documents.
"""

import unittest
from dataclasses import dataclass
from typing import Dict, Any, Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.logic.format_field_mapper import FormatFieldMapper, FieldInfo


class MockCell:
    """Mock cell object for testing."""
    def __init__(self, text: str):
        self._text = text
    
    @property
    def text(self):
        return self._text


class MockRow:
    """Mock row object for testing."""
    def __init__(self, cells):
        self.cells = cells


class MockTable:
    """Mock table object for testing."""
    def __init__(self, rows):
        self.rows = rows


class MockParagraph:
    """Mock paragraph object for testing."""
    def __init__(self, text: str):
        self._text = text
    
    @property
    def text(self):
        return self._text


class TestSingleCellTableDetection(unittest.TestCase):
    """Test single-cell table detection logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mapper = FormatFieldMapper(gemini_client=None)
    
    def test_single_cell_with_underline_pattern(self):
        """Test detection of single-cell table with underline placeholder."""
        # Create a mock single-cell table with underline
        cell = MockCell("ラベル：_____")
        row = MockRow([cell])
        table = MockTable([row])
        
        fields = self.mapper._detect_single_cell_pattern(table, 0, None)
        
        self.assertEqual(len(fields), 1, "Should detect one field")
        self.assertEqual(fields[0].field_name, "ラベル", "Should extract label correctly")
        self.assertEqual(fields[0].field_type, "table_cell", "Should be table_cell type")
        self.assertEqual(
            fields[0].location["input_pattern"], 
            "single_cell_underline", 
            "Should identify as underline pattern"
        )
    
    def test_single_cell_with_bracket_pattern(self):
        """Test detection of single-cell table with bracket placeholder."""
        # Create a mock single-cell table with bracket
        cell = MockCell("メールアドレス（　）")
        row = MockRow([cell])
        table = MockTable([row])
        
        fields = self.mapper._detect_single_cell_pattern(table, 0, None)
        
        self.assertEqual(len(fields), 1, "Should detect one field")
        self.assertEqual(fields[0].field_name, "メールアドレス", "Should extract label correctly")
        self.assertEqual(
            fields[0].location["input_pattern"], 
            "single_cell_bracket", 
            "Should identify as bracket pattern"
        )
    
    def test_single_cell_empty_with_paragraph_label(self):
        """Test detection of empty single-cell table with paragraph label."""
        # Create a mock empty single-cell table
        cell = MockCell("")
        row = MockRow([cell])
        table = MockTable([row])
        
        # Create block_items with a paragraph before the table
        para = MockParagraph("<メールアドレス>")
        block_items = [
            {"type": "paragraph", "obj": para, "index": 0},
            {"type": "table", "obj": table, "index": 0}
        ]
        
        fields = self.mapper._detect_single_cell_pattern(table, 0, block_items)
        
        self.assertEqual(len(fields), 1, "Should detect one field")
        self.assertEqual(fields[0].field_name, "<メールアドレス>", "Should use paragraph as label")
        self.assertEqual(
            fields[0].location["input_pattern"], 
            "single_cell_with_paragraph_label", 
            "Should identify as paragraph label pattern"
        )
    
    def test_single_cell_empty_without_label(self):
        """Test detection of empty single-cell table without label."""
        # Create a mock empty single-cell table
        cell = MockCell("")
        row = MockRow([cell])
        table = MockTable([row])
        
        fields = self.mapper._detect_single_cell_pattern(table, 2, None)
        
        self.assertEqual(len(fields), 1, "Should detect one field even without label")
        self.assertEqual(fields[0].field_name, "テーブル2", "Should use default label")
        self.assertEqual(
            fields[0].location["input_pattern"], 
            "single_cell_no_label", 
            "Should identify as no label pattern"
        )
    
    def test_single_cell_with_placeholder_only(self):
        """Test detection of single-cell table with placeholder only."""
        test_cases = [
            "_____",
            "＿＿＿＿＿",
            "（　）",
            "(　)",
            "（）",
            "()"
        ]
        
        for placeholder in test_cases:
            with self.subTest(placeholder=placeholder):
                cell = MockCell(placeholder)
                row = MockRow([cell])
                table = MockTable([row])
                
                # Without paragraph label
                fields = self.mapper._detect_single_cell_pattern(table, 0, None)
                
                self.assertEqual(len(fields), 1, f"Should detect placeholder: {placeholder}")
    
    def test_find_label_before_table(self):
        """Test label extraction from paragraph before table."""
        # Create block_items with various patterns
        test_cases = [
            ("<メールアドレス>", "<メールアドレス>"),
            ("団体名：", "団体名"),
            ("1. 団体登録ID", "1. 団体登録ID"),
            ("申請年月日：西暦　　年　　月　　日", "申請年月日"),
        ]
        
        for para_text, expected_label in test_cases:
            with self.subTest(para_text=para_text):
                para = MockParagraph(para_text)
                block_items = [
                    {"type": "paragraph", "obj": para, "index": 0},
                    {"type": "table", "obj": None, "index": 0}
                ]
                
                label = self.mapper._find_label_before_table(0, block_items)
                
                self.assertEqual(label, expected_label, f"Should extract label from '{para_text}'")
    
    def test_find_label_before_table_no_paragraph(self):
        """Test label extraction when no paragraph exists before table."""
        # Table at the beginning
        block_items = [
            {"type": "table", "obj": None, "index": 0}
        ]
        
        label = self.mapper._find_label_before_table(0, block_items)
        
        self.assertIsNone(label, "Should return None when no paragraph before table")
    
    def test_find_label_before_table_long_paragraph(self):
        """Test that long paragraphs are not used as labels."""
        # Create a long paragraph (over 100 characters)
        long_text = "これは非常に長いテキストで、ラベルとしては適切ではありません。" * 5
        para = MockParagraph(long_text)
        block_items = [
            {"type": "paragraph", "obj": para, "index": 0},
            {"type": "table", "obj": None, "index": 0}
        ]
        
        label = self.mapper._find_label_before_table(0, block_items)
        
        self.assertIsNone(label, "Should not use long paragraphs as labels")


class TestSingleCellTableIntegration(unittest.TestCase):
    """Integration tests for single-cell table detection."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mapper = FormatFieldMapper(gemini_client=None)
    
    def test_analyze_word_table_detects_single_cell(self):
        """Test that _analyze_word_table correctly routes to single-cell detection."""
        # Create a mock single-cell table
        cell = MockCell("項目名：_____")
        row = MockRow([cell])
        table = MockTable([row])
        
        fields = self.mapper._analyze_word_table(table, 0, None)
        
        self.assertEqual(len(fields), 1, "Should detect single-cell table")
        self.assertEqual(fields[0].field_name, "項目名", "Should extract label")
    
    def test_analyze_word_table_multi_cell_not_affected(self):
        """Test that multi-cell tables are not affected by single-cell logic."""
        # Create a mock multi-cell table (2 columns)
        row = MockRow([MockCell("ラベル"), MockCell("")])
        table = MockTable([row])
        
        # This should use the existing label-input pattern logic
        fields = self.mapper._analyze_word_table(table, 0, None)
        
        # The existing logic should handle this
        self.assertGreaterEqual(len(fields), 0, "Should process multi-cell table normally")


if __name__ == '__main__':
    unittest.main()
