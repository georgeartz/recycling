import io
import json
import time
from pathlib import Path
from PIL import Image
import numpy as np
import base64
import streamlit as st
from ultralytics import YOLO
import requests
from uszipcode import SearchEngine

# Initialize uszipcode search engine (cached for performance)
@st.cache_resource
def get_zip_search_engine():
    return SearchEngine()


st.set_page_config(page_title="Recyclable Detector", page_icon="recycle_logo.png", layout="wide")

# Logo above title in upper left
st.image("recycle_logo.png", width=40, use_container_width=False)
st.title("Recyclable Item Detector")

# Add menu with Done recycling option
col1, col2 = st.columns([0.85, 0.15])
with col2:
    menu_option = st.selectbox("⋮", options=["Rerun","Done recycling"], index=0, label_visibility="collapsed", key="top_menu")
    if menu_option == "Done recycling":
        st.success("Thank you for recycling! 😊")
        st.balloons()
        st.stop()

st.markdown("Upload a photo and the app will try to detect common recyclable items (e.g., bottles, cups).")

uploaded = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png"])
zip_code = st.text_input("Enter ZIP code (optional, 5-digit) for local recycling rules", max_chars=5)


def load_rules():
    """Load hierarchical recycling rules from JSON file."""
    rules_path = Path(__file__).parent / "recycling_rules.json"
    if rules_path.exists():
        try:
            return json.loads(rules_path.read_text())
        except Exception:
            return {
                "zips": {},
                "cities": {},
                "states": {},
                "national_default": {}
            }
    return {
        "zips": {},
        "cities": {},
        "states": {},
        "national_default": {}
    }


def validate_zip(zip_code: str) -> bool:
    """Validate that the ZIP code is a real 5-digit US ZIP code."""
    if not zip_code or len(zip_code) != 5 or not zip_code.isdigit():
        return False
    
    search = get_zip_search_engine()
    result = search.by_zipcode(zip_code)
    return result and result.zipcode is not None


def zip_to_location(zip_code: str) -> dict | None:
    """Resolve ZIP code to city, county, and state information."""
    search = get_zip_search_engine()
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


def get_recycling_rules(zip_code: str, rules_map: dict) -> tuple[dict, str]:
    """
    Get recycling rules using tiered resolution.
    Returns (rules_dict, source_label) where source_label describes where rules came from.
    
    Resolution order:
    1. Exact ZIP match
    2. City match (via uszipcode lookup)
    3. State match (via uszipcode lookup)
    4. 3-digit ZIP prefix (regional fallback)
    5. National default
    """
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


def generate_lookup_links(zip_code: str, location: dict | None) -> dict:
    """Generate helpful lookup links when no cached rules exist."""
    city = location.get("city", "") if location else ""
    state = location.get("state_abbr", "") if location else ""
    
    location_str = f"{city}, {state}" if city and state else f"ZIP {zip_code}"
    
    return {
        "default": f"No cached rules for {location_str}. Use the links below to find local recycling information.",
        "earth911_link": f"https://search.earth911.com/?query=recycling&postal_code={zip_code}",
        "company": f"Search earth911.com or contact your local waste management for {location_str}",
        "_fetched_at": int(time.time())
    }


def fetch_and_save_recycling_rules(zip_code: str, rules_map: dict) -> dict:
    """
    Generate helpful recycling lookup information for a ZIP code.
    Since we don't have a real API key, we generate useful links instead.
    """
    location = zip_to_location(zip_code)
    
    # Generate lookup links and info
    new_rules = generate_lookup_links(zip_code, location)
    
    # Also provide some generic guidance based on location if available
    if location:
        new_rules.update({
            "bottle": f"Most areas accept bottles in curbside recycling. Check {location['city']}'s municipal website.",
            "cup": "Compostable cups may be accepted if your area has organics collection; otherwise trash.",
            "wine glass": "Typically not accepted curbside; check for glass drop-off centers in your area.",
            "vase": f"Glass items may require special handling. Contact {location['city']} waste management.",
        })
    
    return new_rules


def save_rules(rules_map: dict) -> bool:
    """Save rules map back to JSON file."""
    rules_path = Path(__file__).parent / "recycling_rules.json"
    try:
        rules_path.write_text(json.dumps(rules_map, indent=2))
        return True
    except Exception as e:
        st.error(f"Failed to save rules: {e}")
        return False


rules_map = load_rules()

# Admin: structured editor for the local recycling_rules.json
admin = st.checkbox("Admin mode: edit recycling rules")
if admin:
    st.markdown("### Admin: Recycling rules editor")
    
    # Admin scope selection
    admin_scope = st.radio("Edit rules for:", ["ZIP codes", "Cities", "States", "National defaults"], horizontal=True)
    
    if admin_scope == "ZIP codes":
        zips = sorted(list(rules_map.get("zips", {}).keys()))
        col1, col2 = st.columns([1, 2])
        with col1:
            zip_choice = st.selectbox("Select ZIP", options=["-- new ZIP --"] + zips, key="zip_select")
            new_zip = st.text_input("New ZIP (5 digits)", max_chars=5, key="new_zip")
            if st.button("Create ZIP"):
                if new_zip and validate_zip(new_zip):
                    if new_zip in rules_map.get("zips", {}):
                        st.warning("ZIP already exists")
                    else:
                        if "zips" not in rules_map:
                            rules_map["zips"] = {}
                        rules_map["zips"][new_zip] = {"default": "No specific instruction available."}
                        st.success(f"Created {new_zip}")
                else:
                    st.error("Enter a valid 5-digit US ZIP code")
        
        # Determine selected ZIP
        selected_zip = None
        if zip_choice and zip_choice != "-- new ZIP --":
            selected_zip = zip_choice
        elif new_zip and new_zip in rules_map.get("zips", {}):
            selected_zip = new_zip
        
        if selected_zip:
            st.subheader(f"Rules for ZIP {selected_zip}")
            local = rules_map.get("zips", {}).get(selected_zip, {})
            
            # Show location info
            location = zip_to_location(selected_zip)
            if location:
                st.info(f"📍 {location['city']}, {location['state_abbr']} ({location['county']} County)")
            
            # Allow editing the rules
            _edit_rule_set(local, selected_zip, rules_map, "zips")
    
    elif admin_scope == "Cities":
        cities = sorted(list(rules_map.get("cities", {}).keys()))
        city_choice = st.selectbox("Select city", options=["-- new city --"] + cities, key="city_select")
        new_city = st.text_input("New city (format: 'City, ST')", key="new_city")
        if st.button("Create city"):
            if new_city and ", " in new_city:
                if new_city in rules_map.get("cities", {}):
                    st.warning("City already exists")
                else:
                    if "cities" not in rules_map:
                        rules_map["cities"] = {}
                    rules_map["cities"][new_city] = {"default": "No specific instruction available."}
                    st.success(f"Created {new_city}")
            else:
                st.error("Enter city in format: 'City, ST' (e.g., 'Seattle, WA')")
        
        selected_city = city_choice if city_choice != "-- new city --" else (new_city if new_city in rules_map.get("cities", {}) else None)
        if selected_city:
            st.subheader(f"Rules for {selected_city}")
            local = rules_map.get("cities", {}).get(selected_city, {})
            _edit_rule_set(local, selected_city, rules_map, "cities")
    
    elif admin_scope == "States":
        states = sorted(list(rules_map.get("states", {}).keys()))
        state_choice = st.selectbox("Select state", options=["-- new state --"] + states, key="state_select")
        new_state = st.text_input("New state (2-letter abbreviation)", max_chars=2, key="new_state")
        if st.button("Create state"):
            if new_state and len(new_state) == 2:
                new_state = new_state.upper()
                if new_state in rules_map.get("states", {}):
                    st.warning("State already exists")
                else:
                    if "states" not in rules_map:
                        rules_map["states"] = {}
                    rules_map["states"][new_state] = {"default": "No specific instruction available."}
                    st.success(f"Created {new_state}")
            else:
                st.error("Enter 2-letter state abbreviation")
        
        selected_state = state_choice if state_choice != "-- new state --" else (new_state.upper() if new_state and new_state.upper() in rules_map.get("states", {}) else None)
        if selected_state:
            st.subheader(f"Rules for {selected_state}")
            local = rules_map.get("states", {}).get(selected_state, {})
            _edit_rule_set(local, selected_state, rules_map, "states")
    
    else:  # National defaults
        st.subheader("National default rules")
        local = rules_map.get("national_default", {})
        _edit_rule_set(local, "national_default", rules_map, "national_default")


def _edit_rule_set(local: dict, key: str, rules_map: dict, scope: str):
    """Helper function to edit a set of recycling rules."""
    # Allow editing the waste service provider / company name
    company_val = local.get("company", "")
    company_val = st.text_input("Waste service provider (company name)", value=company_val, key=f"company_{key}")
    if company_val:
        local["company"] = company_val
    
    # Display and edit existing rules
    for item in list(local.keys()):
        instr = st.text_input(f"Instruction for '{item}'", value=local[item], key=f"instr_{key}_{item}")
        local[item] = instr
        if st.button(f"Remove {item}", key=f"rm_{key}_{item}"):
            local.pop(item, None)
            st.rerun()
    
    # Add or update an item
    st.markdown("**Add or update item**")
    new_item = st.text_input("Item name", key=f"new_item_{key}")
    new_instr = st.text_input("Instruction", key=f"new_instr_{key}")
    if st.button("Add/Update item", key=f"add_{key}"):
        if new_item:
            local[new_item] = new_instr or ""
            st.success(f"Added/Updated '{new_item}'")
        else:
            st.error("Enter an item name")
    
    # Save rules back to file
    if st.button("Save rules to file", key=f"save_{key}"):
        # Update the rules_map with the edited local rules
        if scope == "national_default":
            rules_map["national_default"] = local
        else:
            if scope not in rules_map:
                rules_map[scope] = {}
            rules_map[scope][key] = local
        
        if save_rules(rules_map):
            st.success("Saved recycling_rules.json")

@st.cache_resource
def load_model():
    return YOLO("yolov8n.pt")

RECYCLABLE_COCO = {
    "bottle",
    "cup",
    "wine glass",
    "vase",
}

if uploaded:
    image_data = uploaded.read()
    img = Image.open(io.BytesIO(image_data)).convert("RGB")
    
    # Display images at half size
    def _render_responsive_image(pil_img, caption=None):
        if caption:
            st.markdown(f"**{caption}**")
        st.image(pil_img, width=400)

    _render_responsive_image(img, caption="Uploaded image")

    with st.spinner("Running detection..."):
        model = load_model()
        results = model(np.array(img), imgsz=640)

    # results is a Results object list; take first
    r = results[0]
    annotated = r.plot()

    # Extract detected class names and confidences
    detected = []
    if hasattr(r, "boxes") and r.boxes is not None and len(r.boxes) > 0:
        for box in r.boxes:
            # cls_idx = int(box.cls.cpu().numpy()) if hasattr(box, "cls") else None
            cls_idx = int(box.cls.cpu().numpy()[0]) if hasattr(box, "cls") else None
            conf = float(box.conf.cpu().numpy()[0]) if hasattr(box, "conf") else None
            name = r.names[cls_idx] if cls_idx is not None else ""
            detected.append((name, conf))

    # Filter recyclable
    recyclable_found = [d for d in detected if d[0] in RECYCLABLE_COCO]

    st.header("Detection Results")
    _render_responsive_image(Image.fromarray(annotated), caption="Detections")

    if detected:
        st.subheader("All detected objects")
        for name, conf in detected:
            st.write(f"- {name} — {conf:.2f}")
    else:
        st.write("No objects detected.")

    st.subheader("Potential Recyclable Items")
    if recyclable_found:
        for name, conf in recyclable_found:
            st.success(f"{name} — {conf:.2f}")

        # Show local recycling instructions when ZIP code provided
        if zip_code:
            # Validate ZIP code first
            if not validate_zip(zip_code):
                st.error(f"'{zip_code}' is not a valid US ZIP code. Please enter a valid 5-digit ZIP code.")
            else:
                # Get recycling rules using tiered lookup
                local_rules, source = get_recycling_rules(zip_code, rules_map)
                
                st.subheader("♻️ Local Recycling Instructions")
                
                # Show location info
                location = zip_to_location(zip_code)
                if location:
                    st.caption(f"📍 {location['city']}, {location['state_abbr']} ({location['county']} County)")
                
                # Show rule source
                st.caption(f"ℹ️ Rules source: {source}")
                
                # Always show the waste management company/provider
                provider = local_rules.get("company") or local_rules.get("service_provider") or local_rules.get("provider")
                if provider:
                    st.info(f"**Waste service provider:** {provider}")
                
                # Show Earth911 link if it exists
                if "earth911_link" in local_rules:
                    st.markdown(f"🔍 [Search for recycling centers near you]({local_rules['earth911_link']})")
                
                # Show recycling instructions for detected items
                st.markdown("**Instructions for detected items:**")
                for name, conf in recyclable_found:
                    instr = local_rules.get(name, local_rules.get("default", "No specific instruction available."))
                    st.write(f"- **{name}**: {instr}")
                
                # Option to show all rules for this location
                show_all_key = f"show_all_rules_{zip_code}"
                if st.checkbox("Show all recycling rules for this location", key=show_all_key):
                    st.subheader(f"All rules for {source}")
                    if local_rules:
                        # Skip special keys when showing all rules
                        skip_keys = {"company", "service_provider", "provider", "earth911_link", "_fetched_at"}
                        for k, v in local_rules.items():
                            if k not in skip_keys:
                                st.write(f"- **{k}**: {v}")
                    else:
                        st.write("No rules available.")
                
                # If using national defaults, offer to cache local rules
                if source == "national default" or "earth911_link" in local_rules:
                    if st.button(f"💾 Cache rules for ZIP {zip_code}", key=f"cache_{zip_code}"):
                        with st.spinner(f"Generating lookup information for {zip_code}..."):
                            fetched_rules = fetch_and_save_recycling_rules(zip_code, rules_map)
                            if "zips" not in rules_map:
                                rules_map["zips"] = {}
                            rules_map["zips"][zip_code] = fetched_rules
                            if save_rules(rules_map):
                                st.success(f"Cached lookup information for {zip_code}!")
                                st.rerun()
    else:
        st.info("No common recyclable items detected using the default COCO classes.")

    st.write("---")
    st.write("Notes: This uses a general-purpose COCO-pretrained YOLOv8 model. For higher accuracy on specific recyclable categories (plastic types, cardboard, cans), custom training is recommended.")
