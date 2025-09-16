from __future__ import annotations
from typing import List

BENEFIT_KEYWORDS = [
    '401k','401(k)','401k match','health insurance','medical','dental','vision','pto','paid time off','bonus','annual bonus','performance bonus','stock','equity','rsu','espp','life insurance','disability','hsa','fsa','commuter','parental leave','maternity leave','paternity leave','parental benefits','flexible schedule','flex time','gym stipend','wellness','mental health','tuition','education reimbursement','learning stipend','unlimited pto','transportation stipend'
]

def extract_benefits(description: str | None) -> List[str]:
    if not description:
        return []
    dlow = description.lower()
    out = []
    for b in BENEFIT_KEYWORDS:
        if b in dlow:
            out.append(b.replace('(k)','k'))
    # Deduplicate while preserving order
    seen = set()
    dedup = []
    for item in out:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup
