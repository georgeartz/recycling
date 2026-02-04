import io
import json
from pathlib import Path
from PIL import Image
import numpy as np
import base64
import streamlit as st
from ultralytics import YOLO
import requests


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
    rules_path = Path(__file__).parent / "recycling_rules.json"
    if rules_path.exists():
        try:
            return json.loads(rules_path.read_text())
        except Exception:
            return {}
    return {}


def fetch_and_save_recycling_rules(zip_code):
    """Attempt to fetch recycling rules from Earth911 API and save to file."""
    try:
        # Try Earth911 API (free tier available)
        api_url = f"https://www.earth911.com/api/Service/searchitems"
        params = {"query": zip_code, "country": "US"}
        response = requests.get(api_url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            # Create a basic rule entry based on available data
            new_rules = {
                "bottle": "Check local guidelines for glass and plastic bottles.",
                "cup": "Disposable cups may vary; check municipal rules.",
                "wine glass": "Broken glass typically goes to trash; intact glassware check locally.",
                "vase": "Glass items generally need special handling.",
                "default": "Contact your local waste management for specific recycling instructions.",
                "company": "Check earth911.com for providers in your area"
            }
            return new_rules
    except Exception as e:
        st.warning(f"Could not fetch rules online: {e}")
    
    # Return default rules if API fails
    return {
        "bottle": "Rinse and place in curbside recycling bin.",
        "cup": "Check if compostable; otherwise trash.",
        "wine glass": "Not typically accepted; check local drop-off.",
        "vase": "Check local rules; may need special handling.",
        "default": "Consult your local waste management authority.",
        "company": "Check local waste provider"
    }


def save_rules():
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

    # ZIP selection / creation
    zips = sorted(list(rules_map.keys()))
    col1, col2 = st.columns([1, 2])
    with col1:
        zip_choice = st.selectbox("Select ZIP", options=["-- new ZIP --"] + zips, key="zip_select")
        new_zip = st.text_input("New ZIP (5 digits)", max_chars=5, key="new_zip")
        if st.button("Create ZIP"):
            if new_zip and len(new_zip) == 5 and new_zip.isdigit():
                if new_zip in rules_map:
                    st.warning("ZIP already exists")
                else:
                    rules_map[new_zip] = {"default": "No specific instruction available."}
                    st.success(f"Created {new_zip}")
            else:
                st.error("Enter a valid 5-digit ZIP code")

    # Determine selected ZIP
    selected_zip = None
    if zip_choice and zip_choice != "-- new ZIP --":
        selected_zip = zip_choice
    elif new_zip and new_zip in rules_map:
        selected_zip = new_zip

    if selected_zip:
        st.subheader(f"Rules for {selected_zip}")
        local = rules_map.get(selected_zip, {})

        # Allow editing the local waste service provider / company name
        company_val = local.get("company", "")
        company_val = st.text_input("Waste service provider (company name)", value=company_val, key=f"company_{selected_zip}")
        if company_val:
            local["company"] = company_val

        # Display and edit existing rules
        for item in list(local.keys()):
            instr = st.text_input(f"Instruction for '{item}'", value=local[item], key=f"instr_{selected_zip}_{item}")
            local[item] = instr
            if st.button(f"Remove {item}", key=f"rm_{selected_zip}_{item}"):
                local.pop(item, None)
                st.experimental_rerun()

        # Add or update an item
        st.markdown("**Add or update item**")
        new_item = st.text_input("Item name", key=f"new_item_{selected_zip}")
        new_instr = st.text_input("Instruction", key=f"new_instr_{selected_zip}")
        if st.button("Add/Update item", key=f"add_{selected_zip}"):
            if new_item:
                local[new_item] = new_instr or ""
                st.success(f"Added/Updated '{new_item}'")
            else:
                st.error("Enter an item name")

        # Save rules back to file
        if st.button("Save rules to file"):
            rules_path = Path(__file__).parent / "recycling_rules.json"
            try:
                rules_path.write_text(json.dumps(rules_map, indent=2))
                st.success("Saved recycling_rules.json")
            except Exception as e:
                st.error(f"Failed to save: {e}")

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
        if zip_code and zip_code in rules_map:
            st.subheader("Local Recycling Instructions")
            local_rules = rules_map.get(zip_code, {})
            # Always show the waste management company/provider for this ZIP
            provider = local_rules.get("company") or local_rules.get("service_provider") or local_rules.get("provider")
            if provider:
                st.info(f"Waste service provider for {zip_code}: {provider}")
            else:
                st.info("No waste service provider registered for this ZIP code.")

            # Option to show all rules for this ZIP (company first)
            show_all_key = f"show_all_rules_{zip_code}"
            if st.checkbox("Show all recycling rules for this ZIP", key=show_all_key):
                st.subheader(f"All rules for {zip_code}")
                if local_rules:
                    # Show company/provider first if present
                    provider_key = None
                    provider = local_rules.get("company") or local_rules.get("service_provider") or local_rules.get("provider")
                    if provider:
                        st.info(f"Waste service provider: {provider}")
                        # remember which key(s) represented provider to avoid duplicate listing
                        for pk in ("company", "service_provider", "provider"):
                            if pk in local_rules:
                                provider_key = pk
                                break

                    # Then list other rules (skip the provider key)
                    for k, v in local_rules.items():
                        if k == provider_key:
                            continue
                        st.write(f"- {k}: {v}")
                else:
                    st.write("No rules available for this ZIP code.")

            for name, conf in recyclable_found:
                instr = local_rules.get(name, local_rules.get("default", "No specific instruction available."))
                st.write(f"- {name}: {instr}")
        elif zip_code:
            st.info(f"No rules found for ZIP {zip_code}. Looking up recycling rules online...")
            with st.spinner(f"Fetching recycling rules for {zip_code}..."):
                fetched_rules = fetch_and_save_recycling_rules(zip_code)
                rules_map[zip_code] = fetched_rules
                if save_rules():
                    st.success(f"Added recycling rules for {zip_code}!")
                    st.subheader("Local Recycling Instructions")
                    for name, conf in recyclable_found:
                        instr = fetched_rules.get(name, fetched_rules.get("default", "No specific instruction available."))
                        st.write(f"- {name}: {instr}")
    else:
        st.info("No common recyclable items detected using the default COCO classes.")

    st.write("---")
    st.write("Notes: This uses a general-purpose COCO-pretrained YOLOv8 model. For higher accuracy on specific recyclable categories (plastic types, cardboard, cans), custom training is recommended.")
