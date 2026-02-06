#!/usr/bin/env python3
"""
Test script to verify the tiered ZIP code lookup logic.
"""

import json
from pathlib import Path
from uszipcode import SearchEngine

# Load the rules
rules_path = Path(__file__).parent / "recycling_rules.json"
rules_map = json.loads(rules_path.read_text())

# Initialize uszipcode
search = SearchEngine()

def zip_to_location(zip_code: str):
    """Resolve ZIP code to city, county, and state information."""
    result = search.by_zipcode(zip_code)
    
    if result and result.zipcode:
        return {
            "zipcode": result.zipcode,
            "city": result.major_city or result.post_office_city,
            "county": result.county,
            "state": result.state,
            "state_abbr": result.state_abbr,
        }
    return None

def get_recycling_rules(zip_code: str, rules_map: dict):
    """Get recycling rules using tiered resolution."""
    # Tier 1: Exact ZIP
    zips = rules_map.get("zips", {})
    if zip_code in zips:
        return zips[zip_code], f"ZIP {zip_code}"
    
    # Tier 2 & 3: City/State via uszipcode
    location = zip_to_location(zip_code)
    if location:
        # Try city match
        city_key = f"{location['city']}, {location['state_abbr']}"
        cities = rules_map.get("cities", {})
        if city_key in cities:
            return cities[city_key], city_key
        
        # Try state match
        state_abbr = location["state_abbr"]
        states = rules_map.get("states", {})
        if state_abbr in states:
            return states[state_abbr], f"{state_abbr} (state-level)"
    
    # Tier 4: 3-digit prefix (SCF region)
    if len(zip_code) >= 3:
        prefix = zip_code[:3]
        if prefix in zips:
            return zips[prefix], f"region {prefix}xx"
    
    # Tier 5: National default
    national = rules_map.get("national_default", {})
    return national, "national default"

# Test cases
test_cases = [
    ("94105", "Should match exact ZIP in San Francisco"),
    ("94104", "Should match San Francisco city-level"),
    ("95825", "Should match exact ZIP in Sacramento area"),
    ("95826", "Should match CA state-level (neighboring Sacramento)"),
    ("90210", "Should match Los Angeles city-level"),
    ("10001", "Should match exact ZIP in New York"),
    ("10002", "Should match New York city-level"),
    ("12345", "Should match NY state-level"),
    ("99999", "Should match national default (invalid/remote ZIP)"),
]

print("=" * 80)
print("Testing Tiered ZIP Code Lookup Logic")
print("=" * 80)

for zip_code, description in test_cases:
    print(f"\n🔍 Testing {zip_code}: {description}")
    location = zip_to_location(zip_code)
    
    if location:
        print(f"   📍 Location: {location['city']}, {location['state_abbr']}")
    else:
        print(f"   ❌ Invalid or not found in uszipcode database")
        continue
    
    rules, source = get_recycling_rules(zip_code, rules_map)
    print(f"   ✅ Rules source: {source}")
    
    # Show bottle rule as example
    bottle_rule = rules.get("bottle", "No rule")
    print(f"   📦 Bottle rule: {bottle_rule[:80]}...")
    
    # Show company if available
    company = rules.get("company", "N/A")
    print(f"   🏢 Company: {company}")

print("\n" + "=" * 80)
print("✨ Test completed!")
print("=" * 80)
