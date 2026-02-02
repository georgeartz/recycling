# Recyclable Item Detector

Minimal demo app that uses a pretrained YOLOv8 model to detect common recyclable-looking objects (e.g., bottles, cups) in an uploaded photo.

Quick start

1. Create and activate a virtual environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the Streamlit app:

```bash
streamlit run app.py
```

Notes
- The app uses `yolov8n.pt` (ultralytics) which will be downloaded automatically on first run.
- The default COCO classes don't exactly map to all recyclable categories (e.g., cans, cardboard). For higher accuracy create a labeled dataset and fine-tune or train a custom model.

ZIP-code based rules
- Enter a 5-digit ZIP code in the app to apply local recycling instructions defined in `recycling_rules.json`.
- `recycling_rules.json` contains example mappings for a few ZIP codes; extend it with your municipality's rules or integrate a realtime API.

Next steps
- Expand recyclable class list and retrain a model for fine-grained categories.
- Add batching / mobile optimizations for on-device inference.
