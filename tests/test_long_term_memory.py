"""Test script for long-term memory functionality."""

import sys
import os
import pytest

pytestmark = pytest.mark.side_effect

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.memory import LongTermMemory


def test_memory():
    print("=" * 50)
    print("Testing Long-Term Memory")
    print("=" * 50)
    
    # Initialize
    m = LongTermMemory()
    print(f"\n1. DB Path: {m.db_path}")
    print(f"   DB exists: {os.path.exists(m.db_path)}")
    
    # Clear any existing data for clean test
    print("\n2. Clearing existing memories...")
    m.clear_all()
    
    # Test save
    print("\n3. Testing save...")
    id1 = m.save("User's name is Mohit", "name")
    print(f"   Saved name memory: {id1}")
    
    id2 = m.save("User lives in Una, Himachal Pradesh", "location")
    print(f"   Saved location memory: {id2}")
    
    id3 = m.save("User prefers dark mode", "preference")
    print(f"   Saved preference memory: {id3}")
    
    # Test retrieve
    print("\n4. Testing get_all...")
    all_mems = m.get_all()
    print(f"   Total memories: {len(all_mems)}")
    for mem in all_mems:
        print(f"   - [{mem['category']}] {mem['content']}")
    
    # Test context string
    print("\n5. Testing get_context_string...")
    context = m.get_context_string()
    print(context)
    
    # Test search
    print("\n6. Testing search...")
    results = m.search("Mohit")
    print(f"   Results for 'Mohit': {len(results)}")
    for r in results:
        print(f"   - {r['content']}")
    
    # Test update (similar content)
    print("\n7. Testing update (similar content)...")
    id4 = m.save("User's name is Mohit Rawat", "name")
    all_mems = m.get_all()
    print(f"   Total memories after update: {len(all_mems)} (should still be 3, not 4)")
    for mem in all_mems:
        print(f"   - [{mem['category']}] {mem['content']}")
    
    print("\n" + "=" * 50)
    print("All tests completed!")
    print("=" * 50)


if __name__ == "__main__":
    test_memory()
