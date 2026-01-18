"""
Simple manual test for URLAnalyzer.
Tests basic URL analysis functionality.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.url_analyzer import URLAnalyzer


async def test_url_analyzer():
    """Test URLAnalyzer with a simple URL."""
    print("=" * 60)
    print("URLAnalyzer Manual Test")
    print("=" * 60)
    
    analyzer = URLAnalyzer()
    
    # Test with example.com
    test_url = "https://www.example.com"
    print(f"\nTest 1: Analyzing {test_url}")
    print("-" * 60)
    
    result = await analyzer.analyze_url(test_url)
    
    if result.get('success'):
        print("✓ SUCCESS")
        print(f"  Title: {result.get('title')}")
        print(f"  URL: {result.get('url')}")
        print(f"  Description: {result.get('description')}")
        print(f"  Content (first 200 chars): {result.get('content_summary')[:200]}...")
    else:
        print("✗ FAILED")
        print(f"  Error: {result.get('error')}")
    
    # Test with invalid URL
    invalid_url = "https://this-does-not-exist-12345.invalid"
    print(f"\nTest 2: Analyzing invalid URL {invalid_url}")
    print("-" * 60)
    
    result2 = await analyzer.analyze_url(invalid_url)
    
    if result2.get('success'):
        print("✗ UNEXPECTED SUCCESS - should have failed")
    else:
        print("✓ CORRECTLY FAILED")
        print(f"  Error: {result2.get('error')}")
    
    # Test multiple URLs
    urls = ["https://www.example.com", "https://www.example.org"]
    print(f"\nTest 3: Analyzing multiple URLs")
    print("-" * 60)
    
    results = await analyzer.analyze_urls(urls)
    
    successful = sum(1 for r in results if r.get('success'))
    print(f"✓ Analyzed {len(results)} URLs, {successful} successful")
    
    for i, r in enumerate(results, 1):
        status = "✓" if r.get('success') else "✗"
        title = r.get('title', 'N/A') if r.get('success') else r.get('error')
        print(f"  {status} URL {i}: {title}")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_url_analyzer())
