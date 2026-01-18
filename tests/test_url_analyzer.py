"""
Unit tests for URLAnalyzer.

Tests the URL analysis functionality using SiteExplorer.
"""

import pytest
import asyncio
from src.tools.url_analyzer import URLAnalyzer


@pytest.mark.asyncio
async def test_analyze_url_success():
    """Test successful URL analysis."""
    analyzer = URLAnalyzer()
    
    # Use a simple, stable website for testing
    result = await analyzer.analyze_url("https://www.example.com")
    
    assert result is not None
    assert result.get('success') is True
    assert 'title' in result
    assert 'url' in result
    assert 'content_summary' in result


@pytest.mark.asyncio
async def test_analyze_url_invalid():
    """Test analysis with invalid URL."""
    analyzer = URLAnalyzer()
    
    # Use an invalid URL
    result = await analyzer.analyze_url("https://this-is-definitely-not-a-real-domain-12345.com")
    
    assert result is not None
    assert result.get('success') is False
    assert 'error' in result


@pytest.mark.asyncio
async def test_analyze_multiple_urls():
    """Test analysis of multiple URLs."""
    analyzer = URLAnalyzer()
    
    urls = [
        "https://www.example.com",
        "https://www.example.org"
    ]
    
    results = await analyzer.analyze_urls(urls)
    
    assert len(results) == 2
    assert all('success' in r for r in results)


@pytest.mark.asyncio
async def test_content_summary_length():
    """Test that content summary is properly truncated."""
    analyzer = URLAnalyzer()
    
    result = await analyzer.analyze_url("https://www.example.com")
    
    if result.get('success'):
        content_summary = result.get('content_summary', '')
        # Should be truncated to around 500 characters
        assert len(content_summary) <= 503  # 500 + "..."


def test_analyzer_initialization():
    """Test URLAnalyzer initialization."""
    analyzer = URLAnalyzer()
    assert analyzer.timeout == 15000  # Default timeout
    
    custom_analyzer = URLAnalyzer(timeout=30000)
    assert custom_analyzer.timeout == 30000


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
