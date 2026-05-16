"""Quick router smoke test.

Run to validate clauses are split and mapped to boxes.
"""
from __future__ import annotations

from src.router.cascading_router import CascadingRouter
import json

r = CascadingRouter()
text = (
    "Patient is a 70-year-old female with history of hypertension and diabetes. "
    "She presents with sudden severe shortness of breath and chest pain. "
    "On exam: BP 85/50, tachycardic. Ordered ECG and troponin. Give aspirin and start oxygen."
)
out = r.map_text_to_boxes(text)
print(json.dumps(out, indent=2))
