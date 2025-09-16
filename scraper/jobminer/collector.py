from __future__ import annotations
"""
Playwright-based collector (scaffold).

IMPORTANT: Automated collection from LinkedIn may violate their Terms of Service.
Use at your own risk. Keep volume low, add delays, and prefer manual/semi-manual methods.
This module is intentionally conservative and minimal.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING
from datetime import datetime, date, timedelta, timezone
import time, random, re, json, yaml
import logging
# NOTE: Playwright is relatively heavy to import. To keep simple utility imports
# (e.g., scoring / parsing helpers) fast, we only import Playwright when actually
# collecting. During type-checking we still expose proper symbols.
if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError  # type: ignore
else:  # Lightweight placeholders for runtime before lazy import
    sync_playwright = None  # type: ignore
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore
    class PlaywrightTimeoutError(Exception):  # type: ignore
        pass
import os
from .settings import SETTINGS
from .benefits import extract_benefits
# Defer heavy imports (Pydantic models + logging handlers) until actually collecting
if TYPE_CHECKING:  # type hints only
    from .models import JobPosting  # noqa: F401

_real_log_event = None
def log_event(event: str, **fields):
    """Lazy wrapper for structured logging; no-op if logging unavailable."""
    if os.getenv('SCRAPER_DISABLE_EVENTS'):
        return
    global _real_log_event
    if _real_log_event is None:
        try:  # attempt real import only on first use
            from .logging_config import log_event as _real_log_event  # type: ignore
        except Exception:
            def _real_log_event(*_a, **_k):  # type: ignore
                return None
    try:
        _real_log_event(event, **fields)  # type: ignore
    except Exception:
        pass

# Currency or code + number range
# Currency/amount pattern (supports code or symbol). Allows ranges like $100k-120k or 100k - 120k if preceded by currency once.
CURRENCY_RGX = re.compile(r"((?:[$€£])|(?:USD|EUR|GBP))?\s?([0-9]{2,}[0-9kK,.]*)\s?(?:(?:-|to|–|—)\s?((?:[$€£])|(?:USD|EUR|GBP))?\s?([0-9]{2,}[0-9kK,.]*))?", re.I)
SALARY_WORDS = re.compile(r"(salary|compensation|pay|earn|annual|year|hour|yr)\b", re.I)
BENEFIT_HINTS_SECTION = re.compile(r"benefits?[:\n]", re.I)

# Mapping for date posted (simplistic relative text parsing)
RELATIVE_DAY_RGX = re.compile(r"(\d+)\s+(day|hour|minute|week|month)s?\s+ago", re.I)
ABSOLUTE_DATE_RGX = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}")

EMPLOYMENT_TYPE_RGX = re.compile(r"\b(full[- ]?time|part[- ]?time|contract|temporary|internship|apprenticeship|freelance|consultant|seasonal)\b", re.I)
WORK_MODE_PATTERNS = [
    (re.compile(r"\b(remote-first|remote)\b", re.I), 'remote'),
    (re.compile(r"\b(hybrid)\b", re.I), 'hybrid'),
    (re.compile(r"\b(on[- ]?site|onsite)\b", re.I), 'onsite'),
]
SENIORITY_RGX = re.compile(r"\b(intern|graduate|junior|entry|associate|mid|senior|sr\.?|staff|principal|lead|director|vp|vice president|chief|cxo|cto|ceo|head)\b", re.I)

USER_AGENT_OVERRIDE = None  # optionally set a stable UA string


def build_search_url(keywords: str, location: str, date_posted: Optional[str] = None, remote: Optional[bool] = None, seniority: Optional[List[str]] = None, geo_id: Optional[str] = None) -> str:
    base = "https://www.linkedin.com/jobs/search/?"
    params = []
    if keywords:
        params.append(f"keywords={keywords.replace(' ', '%20')}")
    if location:
        params.append(f"location={location.replace(' ', '%20')}")
    if geo_id:  # geoId significantly improves result reliability
        params.append(f"geoId={geo_id}")
    # date_posted mapping (LinkedIn internal codes may change; example r604800 ~ past week)
    if date_posted == 'past_week':
        params.append('f_TPR=r604800')
    elif date_posted == 'past_24_hours':
        params.append('f_TPR=r86400')
    elif date_posted == 'past_month':
        params.append('f_TPR=r2592000')
    if remote:
        # remote filter example; LinkedIn may change; placeholder retained
        params.append('f_WT=2')
    if seniority:
        level_map = {
            'Internship': '1', 'Entry': '2', 'Associate': '3', 'Mid-Senior': '4', 'Director': '5', 'Executive': '6'
        }
        codes = [level_map.get(s, '') for s in seniority]
        codes = [c for c in codes if c]
        if codes:
            params.append('f_E=' + '%2C'.join(codes))
    return base + '&'.join(params)


_RUNTIME_CFG_CACHE = None

def _load_runtime_cfg():
    global _RUNTIME_CFG_CACHE
    if _RUNTIME_CFG_CACHE is None:
        try:
            cfg_path = Path('scraper/config/runtime.yml')
            if cfg_path.exists():
                _RUNTIME_CFG_CACHE = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
            else:
                _RUNTIME_CFG_CACHE = {}
        except Exception:
            _RUNTIME_CFG_CACHE = {}
    return _RUNTIME_CFG_CACHE

def _cfg_value(key: str, default: float) -> float:
    cfg = _load_runtime_cfg()
    return float(cfg.get(key, default))

def polite_sleep(min_s=None, max_s=None):
    if min_s is None:
        min_s = SETTINGS.polite_min
    if max_s is None:
        max_s = SETTINGS.polite_max
    if max_s < min_s:
        max_s = min_s
    time.sleep(random.uniform(min_s, max_s))


def parse_posted_relative(text: str) -> Optional[date]:
    m = RELATIVE_DAY_RGX.search(text)
    if not m:
        return None
    val, unit = m.groups()
    try:
        num = int(val)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    unit_l = unit.lower()
    days = 0
    if 'minute' in unit_l or 'hour' in unit_l:
        days = 0
    elif 'day' in unit_l:
        days = num
    elif 'week' in unit_l:
        days = num * 7
    elif 'month' in unit_l:
        days = num * 30
    try:
        return (now.date()) if days == 0 else (now.date() - timedelta(days=days))
    except Exception:
        return now.date()


def parse_posted_text(text: str) -> Optional[date]:
    """Parse a posted-at text fragment that may contain relative or absolute date.
    Returns a date or None.
    """
    if not text:
        return None
    d = parse_posted_relative(text)
    if d:
        return d
    m = ABSOLUTE_DATE_RGX.search(text)
    if m:
        try:
            return datetime.strptime(m.group(0), '%B %d, %Y').date()
        except Exception:
            return None
    return None


LOCATION_FALLBACK_RGX = re.compile(r"\b(based in|located in|headquartered in)\s+([A-Za-z .,'-]{2,60})", re.I)

def derive_location_from_description(description: Optional[str]) -> Optional[str]:
    """Very lightweight location derivation from early lines of description.
    Looks for phrases like 'based in X'. Returns the captured location string.
    """
    if not description:
        return None
    for line in description.splitlines()[:8]:
        m = LOCATION_FALLBACK_RGX.search(line.strip())
        if m:
            loc = m.group(2).strip().strip('.:,;')
            # Basic sanity: at least one space OR one capitalized letter sequence
            if 2 <= len(loc) <= 60:
                return loc
    return None


def extract_salary(description: str):
    """Extract salary; always treat values as annual (no period inference/conversion).
    Returns (min_value, max_value, currency_code, period='year', raw_snippet).
    Supports k notation and currency symbols/codes.
    """
    if not description:
        return None, None, None, None, None
    for line in description.splitlines():
        if SALARY_WORDS.search(line) or CURRENCY_RGX.search(line):
            m = CURRENCY_RGX.search(line)
            if not m:
                continue
            raw_line = line.strip()[:300]
            c1, v1, c2, v2 = m.groups()
            cur = c1 or c2
            # Skip obviously non-salary short numbers (e.g., bullet numbering)
            if v1 and len(v1) <= 2 and not v1.lower().endswith('k') and not v2:
                continue
            def normalize(v: str) -> Optional[float]:
                v = v.lower().replace(',', '')
                mult = 1.0
                if v.endswith('k'):
                    mult = 1000.0
                    v = v[:-1]
                try:
                    return float(v) * mult
                except ValueError:
                    return None
            min_v = normalize(v1)
            max_v = normalize(v2) if v2 else None
            # If no currency symbol but range present, keep cur None
            # If only single value treat as both min and max for downstream clarity
            if max_v is None and min_v is not None:
                max_v = min_v
            return min_v, max_v, currency_symbol_to_code(cur) if cur else None, 'year', raw_line
    return None, None, None, None, None


def currency_symbol_to_code(sym: str) -> Optional[str]:
    mapping = {'$': 'USD', '€': 'EUR', '£': 'GBP', 'USD':'USD','EUR':'EUR','GBP':'GBP'}
    return mapping.get(sym.upper()) if sym else None


def secondary_location_scan_factory(page: Page):
    def _inner(existing_location: Optional[str], existing_mode: Optional[str]):
        location_local = existing_location
        mode_local = existing_mode
        try:
            selectors = [
                'div.job-details-jobs-unified-top-card__sticky-header-job-title + div',
                'div.job-details-jobs-unified-top-card__primary-description-container > div > span > span:nth-child(1)',
                'div.artdeco-card.full-width.p5.job-details-module div:nth-child(1) > div > span',
                'div.job-details-fit-level-preferences > button:nth-child(2) > span:nth-child(1) > span > strong > span'
            ]
            tokens = []
            for sel in selectors:
                try:
                    el = page.query_selector(sel)
                    if not el:
                        continue
                    txt = (el.inner_text() or '').strip()
                    if not txt:
                        continue
                    tokens.append(txt)
                    low = txt.lower()
                    if not mode_local and any(k in low for k in ['remote','hybrid','on-site','onsite']):
                        mode_local = 'remote' if 'remote' in low else ('hybrid' if 'hybrid' in low else 'onsite')
                    if (not location_local) and (',' in txt or 'united states' in low) and any(ch.isalpha() for ch in txt):
                        location_local = txt
                except Exception:
                    continue
            return location_local, mode_local, tokens
        except Exception:
            return location_local, mode_local, []
    return _inner

def extract_job_from_panel(page: Page) -> Dict[str, Any]:
    # Defensive selectors; returns partial data
    def safe_text(selector: str):
        try:
            el = page.query_selector(selector)
            if el:
                return el.inner_text().strip()
        except Exception:
            return None
        return None
    def first_text(selectors):
        for sel in selectors:
            t = safe_text(sel)
            if t:
                return t
        return None
    def safe_attr(selector: str, attr: str):
        try:
            el = page.query_selector(selector)
            if el:
                v = el.get_attribute(attr)
                if v:
                    return v.strip()
        except Exception:
            return None
        return None
    # --- Advanced field variant parsers (from provided DOM mapping) ---
    def parse_title_from_variants():
        # Option 1 / 5 main visible title strong/h1
        raw = first_text([
            'div.job-details-jobs-unified-top-card__sticky-header-job-title span strong',  # option 1
            'div.display-flex.justify-space-between.flex-wrap.mt2 h1',                     # option 5
            'div.job-details-jobs-unified-top-card__primary-description-container h1',
        ])
        if raw:
            return raw.replace('\u00a0', ' ').strip()
        # Option 2 visually hidden variant containing suffix 'with verification'
        hidden = first_text(['div.job-details-jobs-unified-top-card__sticky-header-job-title span.visually-hidden'])
        if hidden and 'with verification' in hidden.lower():
            return hidden.split(' with verification')[0].strip()
        # Option 3 / 7 accessibility save button pattern: "Save <job title> at <company>"
        a11y = first_text([
            'div.job-details-jobs-unified-top-card__sticky-header-job-title ~ div button span.a11y-text',
            'div.mt4 button span.a11y-text'
        ])
        if a11y and a11y.lower().startswith('save ') and ' at ' in a11y:
            try:
                return a11y[5:].split(' at ')[0].strip()
            except Exception:
                pass
        # Option 4 / 6 apply button aria-label: "Apply to <job title> on company website"
        aria_apply = (safe_attr('div.jobs-s-apply.jobs-s-apply--fadein.inline-flex.ml2 > div > button', 'aria-label') or
                      safe_attr('div.mt4 > div > div > div > button','aria-label'))
        if aria_apply and aria_apply.lower().startswith('apply to '):
            seg = aria_apply[9:]
            if ' on ' in seg:
                return seg.split(' on ')[0].strip()
        # Option 8 card variant: "<title>, <location>"
        opt8 = safe_text('div.artdeco-card.full-width.p5.job-details-module div:nth-child(1) > div > span')
        if opt8 and ',' in opt8:
            return opt8.split(',')[0].strip()
        return None
    def parse_company_from_variants():
        # Option 1/2/5: company logo anchor aria-label "Company Name logo"
        logo_aria = (safe_attr('div.job-details-jobs-unified-top-card__sticky-header-job-title ~ a[aria-label]','aria-label') or
                     safe_attr('div.display-flex.align-items-center.flex-1 > a[aria-label]','aria-label'))
        if logo_aria and logo_aria.lower().endswith(' logo'):
            return logo_aria[:-5].strip()
        # Option 6 image alt
        img_alt = safe_attr('div.display-flex.align-items-center.flex-1 a img[alt]', 'alt')
        if img_alt and img_alt.lower().endswith(' logo'):
            return img_alt[:-5].strip()
        # Option 3 / Location line: "Company · City, State" (extract before bullet)
        line = safe_text('div.job-details-jobs-unified-top-card__sticky-header-job-title + div')
        if line and '·' in line:
            seg = line.split('·')[0].strip()
            if seg:
                return seg
        # Option 4 / 7 accessibility save button: "Save Job Title at Company"
        a11y = first_text([
            'div.job-details-jobs-unified-top-card__sticky-header-job-title ~ div button span.a11y-text',
            'div.mt4 button span.a11y-text'
        ])
        if a11y and ' at ' in a11y:
            try:
                return a11y.split(' at ')[-1].strip()
            except Exception:
                pass
        return None
    def parse_location_and_mode(current_title: Optional[str]):
        # Option 2: primary description container first span token
        loc_token = safe_text('div.job-details-jobs-unified-top-card__primary-description-container > div > span > span:nth-child(1)')
        raw_line = safe_text('div.job-details-jobs-unified-top-card__sticky-header-job-title + div')
        work_mode_local = None
        location_local = None
        if raw_line and '·' in raw_line:
            parts = [p.strip() for p in raw_line.split('·') if p.strip()]
            if len(parts) >= 2:
                location_local = parts[1]
        if loc_token and not location_local:
            location_local = loc_token
        # Option 3/8: title, City, State pattern -> location after first comma(s)
        if not location_local:
            opt3 = safe_text('div.artdeco-card.full-width.p5.job-details-module div:nth-child(1) > div > span')
            if opt3 and ',' in opt3:
                tail = ','.join(opt3.split(',')[1:]).strip()
                if tail:
                    location_local = tail
        # Work mode inline parenthetical e.g., "Company · City, State (Remote)"
        if location_local and '(' in location_local and ')' in location_local:
            m = re.search(r'\((remote|hybrid|on-?site)\)', location_local, re.I)
            if m:
                work_mode_local = m.group(1).lower().replace('on-site','onsite')
                location_local = re.sub(r'\((remote|hybrid|on-?site)\)', '', location_local, flags=re.I).strip()
        # Title comma fallback: "<title>, City, State" if title has comma and pattern plausible
        if not location_local and current_title and ',' in current_title:
            maybe_loc = ','.join(current_title.split(',')[1:]).strip()
            if 3 <= len(maybe_loc) <= 60 and any(ch.isalpha() for ch in maybe_loc):
                location_local = maybe_loc
        if location_local:
            location_local = location_local.replace('\u00a0',' ').strip().strip(',')
        return location_local, work_mode_local
    def parse_salary_buttons():
        # Option: fit-level preferences button strong text "$150K/yr - $180K/yr"
        txt = safe_text('div.job-details-fit-level-preferences > button:nth-child(1) > span > strong')
        if not txt:
            return None, None, None
        matches = re.findall(r'([$€£]?)(\d+(?:\.\d+)?)[Kk]?', txt)
        if not matches:
            return None, None, None
        nums = []
        curr = None
        for sym,val in matches:
            curr = sym or curr
            try:
                nums.append(float(val) * 1000)
            except Exception:
                continue
        if not nums:
            return None, None, None
        if len(nums) == 1:
            nums.append(nums[0])
        return min(nums), max(nums), currency_symbol_to_code(curr) if curr else None
    def parse_employment_type():
        # Option: third fit-level preferences button
        etxt = safe_text('div.job-details-fit-level-preferences > button:nth-child(3) > span:nth-child(1) > span > strong > span')
        if not etxt:
            return None
        et = etxt.lower()
        if any(k in et for k in ['full','part','contract','intern','temporary','freelance']):
            if 'full' in et:
                return 'full-time'
            if 'part' in et:
                return 'part-time'
            return et.split()[0]
        return None
    def extract_benefits_list():
        items = []
        try:
            for li in page.query_selector_all('div.jobs-details__salary-main-rail-card ul li')[:40]:
                try:
                    tx = (li.inner_text() or '').strip()
                except Exception:
                    continue
                if tx and 2 <= len(tx) <= 120:
                    items.append(tx)
        except Exception:
            pass
        return items

    secondary_location_scan = secondary_location_scan_factory(page)
    # Attempt to expand truncated description if a show more button exists
    try:
        for btn_selector in [
            'button[aria-label*="Show more"]',
            'button.show-more-less-html__button',
            'button.jobs-description__footer-button']:
            btn = page.query_selector(btn_selector)
            if btn:
                try:
                    btn.click()
                    time.sleep(0.5)
                except Exception:
                    pass
    except Exception:
        pass

    def extract_description() -> Optional[str]:
        # Ordered list of likely description containers
        selectors = [
            'div.show-more-less-html__markup',
            'section.show-more-less-html',
            'div.jobs-description-content__text',
            'div.jobs-box__html-content',
            'div#job-details',
            'div.jobs-description__container',
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    txt = el.inner_text().strip()
                    if txt and len(txt) > 40:  # minimal length guard
                        return txt
            except Exception:
                continue
        return None
    title = (
        parse_title_from_variants() or
        safe_text('h2.top-card-layout__title') or
        safe_text('h1.top-card-layout__title') or
        safe_text('h1')
    )
    company = (
        parse_company_from_variants() or
        safe_text('a.topcard__org-name-link') or
        safe_text('span.topcard__flavor') or
        safe_text('span.topcard__company-url a') or
        safe_text('div.topcard__flavor-row a') or
        safe_text('a.jobs-unified-top-card__company-name') or
        safe_text('span.jobs-unified-top-card__company-name') or
        safe_text('div.jobs-unified-top-card__company-name a')
    )
    # Sticky header (new LinkedIn layout) that may bundle title / company / location / work mode tokens
    try:
        sticky = page.query_selector('div.job-details-jobs-unified-top-card__sticky-header-job-title')
        sticky_txt = None
        if sticky:
            sticky_txt = (sticky.inner_text() or '').strip()
        # Example pattern: "Senior Data Engineer  ·  ACME Corp  ·  London, England  ·  Hybrid"
        if sticky_txt and ('·' in sticky_txt or '\n' in sticky_txt):
            # Split on bullet or newline
            raw_tokens = [t.strip() for t in re.split(r'[\n\u00b7]+', sticky_txt) if t.strip()]
            for tok in raw_tokens:
                low = tok.lower()
                # Work mode direct tokens
                if low in {'remote','hybrid','on-site','onsite','on site'}:
                    work_mode_token = 'remote' if 'remote' in low else ('hybrid' if 'hybrid' in low else 'onsite')
                    # Only set later if not already inferred; stash in closure scope via list hack
                    if 'work_mode' not in locals() or not work_mode:  # work_mode var defined later; safe guard
                        work_mode = work_mode_token  # type: ignore
                    continue
                # Company heuristic: pick middle token if we have title already and company still unknown
                if (not company or company == 'Unknown') and 1 <= len(tok.split()) <= 6 and not re.search(r'\d{4}', tok):
                    # Avoid capturing location tokens that contain comma followed by region/state (handled below)
                    if ',' not in tok:
                        company = company or tok
                # Location heuristic: token with comma or multi-word and capitalized
                if (',' in tok or len(tok.split()) <= 5) and not any(x in low for x in ['remote','hybrid','on-site','onsite']) and re.search(r'[A-Za-z]', tok):
                    if (not 'location' in locals()) or not locals().get('location'):  # location set later
                        # Very light filter: must contain at least one capital letter and not solely job terms
                        if any(ch.isupper() for ch in tok):
                            location = tok  # type: ignore
    except Exception:
        pass
    # Pipe-delimited title pattern: "Job Title | Company Name | LinkedIn"
    if not company:
        try:
            raw_title_for_company = page.title()
            if raw_title_for_company and '|' in raw_title_for_company:
                parts = [p.strip() for p in raw_title_for_company.split('|') if p.strip()]
                # Expected at least 3 parts [job title, company, LinkedIn]
                if len(parts) >= 2:
                    candidate = parts[1]
                    if candidate.lower() not in {'linkedin','home'} and 1 <= len(candidate.split()) <= 6:
                        company = candidate
        except Exception:
            pass
    # Attempt meta tag extraction if still missing
    if not company:
        try:
            meta_company = page.query_selector("meta[name='twitter:data1']") or page.query_selector("meta[property='og:site_name']")
            if meta_company:
                content = meta_company.get_attribute('content')
                if content and len(content.strip()) > 1:
                    company = content.strip()
        except Exception:
            pass
    # Attempt JSON script tag parsing (look for companyName key)
    if not company:
        try:
            # First, dedicated JSON-LD scripts (often have hiringOrganization)
            ld_scripts = page.query_selector_all('script[type="application/ld+json"]')
            for sc in ld_scripts:
                try:
                    raw = sc.inner_text() or ''
                    if not raw.strip():
                        continue
                    data: Union[Dict[str, Any], List[Any]] = json.loads(raw)
                    # Traverse for possible organization/company names
                    def find_org(obj):
                        if isinstance(obj, dict):
                            # LinkedIn sometimes nests hiringOrganization / hiringOrganization.name
                            if 'hiringOrganization' in obj:
                                ho = obj['hiringOrganization']
                                if isinstance(ho, dict):
                                    nm = ho.get('name') or ho.get('legalName')
                                    if isinstance(nm, str) and 1 <= len(nm) <= 120:
                                        return nm
                            for k, v in obj.items():
                                if k in ('companyName', 'name') and isinstance(v, str) and 1 <= len(v) <= 120 and ' ' in v:
                                    return v
                                if isinstance(v, (dict, list)):
                                    r = find_org(v)
                                    if r:
                                        return r
                        elif isinstance(obj, list):
                            for it in obj:
                                r = find_org(it)
                                if r:
                                    return r
                        return None
                    found = find_org(data)
                    if found:
                        company = found
                        break
                except Exception:
                    continue
            # Fallback: scan first N general scripts for companyName pattern
            if not company:
                for script in page.query_selector_all('script')[:60]:  # broaden search
                    txt = script.inner_text() or ''
                    if 'companyName' in txt or 'organization' in txt or 'hiringOrganization' in txt:
                        m = re.search(r'"companyName"\s*:\s*"([^"]{2,120})"', txt)
                        if m:
                            company = m.group(1)
                            break
        except Exception:
            pass
    # Heuristic from document title / breadcrumb (option 2 requested, refined)
    if not company:
        try:
            raw_title = page.title()
            if raw_title:
                # Strip trailing "| LinkedIn" or variants
                cleaned = re.sub(r'\s*\|\s*LinkedIn.*$', '', raw_title).strip()
                # If multiple | segments remain, they often form breadcrumbs. Keep for later splitting.
                # Pattern with ' at '
                if ' at ' in cleaned:
                    # Take last segment after ' at '
                    candidate = cleaned.split(' at ')[-1].strip()
                    # Remove trailing role fragments if any (e.g., '- careers')
                    candidate = re.sub(r' - careers?$', '', candidate, flags=re.I)
                    if 1 <= len(candidate.split()) <= 6:
                        company = candidate
                if not company and ' - ' in cleaned:
                    # Often format: Job Title - Company Name
                    parts = [p.strip() for p in cleaned.split(' - ') if p.strip()]
                    if len(parts) >= 2:
                        last = parts[-1]
                        # Simple heuristic: last segment shorter than first and contains no commas with job terms
                        job_terms = {'engineer','manager','director','program','operations','product','marketing','sales','support','specialist','analyst','lead','coordinator','architect'}
                        if not any(t in last.lower() for t in job_terms) or len(last.split()) <= 4:
                            if 1 <= len(last.split()) <= 6:
                                company = last
                # Additional breadcrumb split on ' | ' (keep right-most meaningful token)
                if company and ' | ' in company:
                    crumb_parts = [p.strip() for p in company.split(' | ') if p.strip()]
                    region_terms = {'california','united states','bay area','remote','hybrid'}
                    # Prefer last non-region part
                    for part in reversed(crumb_parts):
                        if not any(rt in part.lower() for rt in region_terms):
                            company = part
                            break
        except Exception:
            pass
    # Additional fallback: og:title meta pattern "Job Title - Company - LinkedIn"
    if not company:
        try:
            ogt = page.query_selector("meta[property='og:title']")
            if ogt:
                ct = ogt.get_attribute('content') or ''
                if ' - ' in ct:
                    parts = [p.strip() for p in ct.split(' - ') if p.strip()]
                    # try middle part if last is LinkedIn
                    if len(parts) >= 3 and parts[-1].lower().startswith('linkedin'):
                        cand = parts[-2]
                        if 1 <= len(cand.split()) <= 6:
                            company = cand
        except Exception:
            pass
    # Regex scan generic scripts for companyName if still Unknown
    if not company:
        try:
            for script in page.query_selector_all('script')[:80]:
                txt = script.inner_text() or ''
                m = re.search(r'companyName\\":\\"([^"\\]{2,120})\\"', txt)
                if m:
                    comp = m.group(1)
                    if 1 <= len(comp.split()) <= 6:
                        company = comp
                        break
        except Exception:
            pass
    # Title comma heuristic: "Role, Company" pattern
    if not company and title and ',' in title:
        seg = title.split(',')[-1].strip()
        role_terms = {'manager','engineer','director','program','operations','product','marketing','sales','specialist','analyst','lead','coordinator','architect','growth','technical','customer','success','general'}
        # Require at least one capitalized word and not mostly role terms
        tokens = seg.split()
        if 1 <= len(tokens) <= 4:
            lower_tokens = {t.lower().strip('()') for t in tokens}
            if len([t for t in tokens if t[:1].isupper()]) >= 1 and len(lower_tokens - role_terms) >= 1:
                company = seg
    # Anchor-based heuristic: pick shortest plausible company link if still missing
    if not company:
        try:
            candidates = []
            for a in page.query_selector_all('a[href*="/company/"]'):
                try:
                    txt = (a.inner_text() or '').strip()
                except Exception:
                    continue
                if not txt or len(txt) > 60:
                    continue
                # Exclude generic or navigation texts
                lower = txt.lower()
                if any(ex in lower for ex in ['see all', 'similar', 'about', 'overview']):
                    continue
                # Must contain at least one alphabetic char
                if not re.search(r'[a-zA-Z]', txt):
                    continue
                # Avoid capturing full job titles accidentally (contain obvious role words and spaces > 6 words)
                role_terms = {'manager','engineer','director','program','operations','product','marketing','sales','specialist','analyst','lead','coordinator','architect'}
                if sum(1 for t in role_terms if t in lower) > 1:
                    continue
                if len(txt.split()) <= 7:
                    candidates.append(txt)
            # Prefer candidate with minimal word count > 0, then shortest length
            if candidates:
                candidates.sort(key=lambda x: (len(x.split()), len(x)))
                company = candidates[0]
        except Exception:
            pass
    # Filter out generic phrases accidentally captured (e.g., expansion buttons)
    if company and company.lower().strip() in { 'show more', 'see more', 'learn more', 'more', 'apply', 'apply now' }:
        company = None
    # Extract description early so downstream fallbacks can use it
    description = extract_description()
    location = safe_text('span.topcard__flavor--bullet') or safe_text('span.jobs-unified-top-card__bullet')
    # Advanced location + work mode parsing
    loc_adv, mode_adv = parse_location_and_mode(title)
    if loc_adv and not location:
        location = loc_adv
    # mode_adv may be None; work_mode initialized later if additional inference needed
    work_mode = mode_adv if mode_adv else None
    # Additional primary description container parsing (new layout)
    try:
        if not location:
            prim = page.query_selector('div.job-details-jobs-unified-top-card__primary-description-container')
            if prim:
                # Collect span tokens
                spans = prim.query_selector_all('span span, span:not(:has(*))') or []
                tokens = []
                for sp in spans:
                    try:
                        tx = (sp.inner_text() or '').strip()
                        if tx and tx not in tokens and len(tx) < 120:
                            tokens.append(tx)
                    except Exception:
                        continue
                # Heuristic: first token with comma and letters or containing a region word
                for tok in tokens:
                    lower = tok.lower()
                    if re.search(r'[a-zA-Z]', tok) and (',' in tok or 'united states' in lower or 'remote' in lower or 'hybrid' in lower or 'onsite' in lower or 'on-site' in lower):
                        if not location and (',' in tok or 'united states' in lower):
                            location = tok
                    # Work mode from tokens if not already
                    if 'remote' in lower and (not work_mode):
                        work_mode = 'remote'
                    elif 'hybrid' in lower and (not work_mode):
                        work_mode = 'hybrid'
                    elif ('on-site' in lower or 'onsite' in lower) and (not work_mode):
                        work_mode = 'onsite'
        # Sticky secondary div sibling (div:nth-child(2) in provided path)
        if (not location or not work_mode) and not prim:
            sticky_secondary = page.query_selector('div.job-details-jobs-unified-top-card__sticky-header-job-title ~ div')
            if sticky_secondary:
                txt = (sticky_secondary.inner_text() or '').strip()
                if txt:
                    parts = [p.strip() for p in re.split(r'[\u00b7\n]+', txt) if p.strip()]
                    for ptxt in parts:
                        low = ptxt.lower()
                        if (not location) and (',' in ptxt or 'united states' in low) and any(ch.isalpha() for ch in ptxt):
                            location = ptxt
                        if (not work_mode) and any(k in low for k in ['remote','hybrid','on-site','onsite']):
                            work_mode = 'remote' if 'remote' in low else ('hybrid' if 'hybrid' in low else 'onsite')
    except Exception:
        pass
    if not location and description:
        location = derive_location_from_description(description)
    posted = safe_text('span.posted-time-ago__text')
    # Direct time tag (more accurate posted date) if available
    try:
        time_el = page.query_selector('time[datetime]')
        if time_el:
            dt_attr = time_el.get_attribute('datetime')
            if dt_attr and re.match(r'\d{4}-\d{2}-\d{2}', dt_attr):
                try:
                    posted = dt_attr  # treat as absolute for parser below
                except Exception:
                    pass
    except Exception:
        pass

    posted_date = parse_posted_text(posted) if posted else None

    # Prefer explicit fit-level salary button extraction first
    sbtn_min, sbtn_max, sbtn_cur = parse_salary_buttons()
    if sbtn_min is not None:
        salary_min, salary_max, salary_cur, salary_period, salary_raw = sbtn_min, sbtn_max, sbtn_cur, 'year', None
    else:
        salary_min, salary_max, salary_cur, salary_period, salary_raw = extract_salary(description or '')
    # Fallback salary extraction from fit-level preferences button region if not found
    if salary_min is None:
        try:
            pref = page.query_selector('div.job-details-fit-level-preferences')
            if pref:
                txt = pref.inner_text() or ''
                if txt:
                    m2 = CURRENCY_RGX.search(txt)
                    if m2:
                        c1, v1, c2, v2 = m2.groups()
                        cur = c1 or c2
                        def normv(v):
                            if not v:
                                return None
                            vv = v.lower().replace(',','')
                            mult = 1
                            if vv.endswith('k'):
                                mult = 1000
                                vv = vv[:-1]
                            try:
                                return float(vv)*mult
                            except Exception:
                                return None
                        mn = normv(v1)
                        mx = normv(v2) if v2 else mn
                        if mn is not None:
                            salary_min, salary_max, salary_cur = mn, mx, currency_symbol_to_code(cur) if cur else None
        except Exception:
            pass
    benefits_list = extract_benefits_list()
    benefits = benefits_list or extract_benefits(description or '')

    # Employment type, work mode, seniority extraction from title + description
    employment_type = parse_employment_type() or None
    # Preserve work_mode from earlier parsing if present; else regex inference below
    work_mode = work_mode if 'work_mode' in locals() and work_mode else None
    seniority = None
    blob = ' '.join(filter(None, [title, description]))
    if blob:
        m = EMPLOYMENT_TYPE_RGX.search(blob)
        if m:
            employment_type = m.group(1).lower().replace(' ', '-')
        # Work mode patterns (priority remote > hybrid > onsite)
        for rgx, label in WORK_MODE_PATTERNS:
            if rgx.search(blob):
                work_mode = label
                break
        sm = SENIORITY_RGX.search(title or '') or SENIORITY_RGX.search(description or '')
        if sm:
            token = sm.group(1).lower()
            mapping = {
                'intern':'intern','graduate':'entry','junior':'entry','entry':'entry','associate':'associate','mid':'mid','senior':'senior','sr.':'senior','sr':'senior','staff':'staff','principal':'principal','lead':'lead','director':'director','vp':'vp','vice president':'vp','chief':'cxo','cxo':'cxo','cto':'cxo','ceo':'cxo','head':'director'
            }
            seniority = mapping.get(token, token)

    # External apply URL (if present)
    apply_url = None
    try:
        ext_link = page.query_selector('a.topcard__link')
        if ext_link:
            href = ext_link.get_attribute('href')
            if href and 'linkedin.com' not in href:
                apply_url = href
    except Exception:
        pass

    apply_method = 'unknown'
    if page.query_selector('button.jobs-apply-button'):
        apply_method = 'linkedin_easy_apply'
    elif page.query_selector('a.topcard__link'):
        apply_method = 'external'

    return {
        'title': title,
        'company_name': company,
        'page_title': None,  # will be filled by caller with page.title() to avoid extra calls here
        'location': location,
        'posted_at': posted_date,
        'description_raw': description,
        'description_clean': description,
        'apply_method': apply_method,
        'offered_salary_min': salary_min,
        'offered_salary_max': salary_max,
    'offered_salary_currency': salary_cur,
        'benefits': benefits,
        'employment_type': employment_type,
        'work_mode': work_mode,
        'seniority_level': seniority,
        'apply_url': apply_url,
    }


def _is_logged_in(page) -> bool:
    try:
        # Presence of global nav / me avatar indicates authenticated state.
        if page.query_selector('nav.global-nav__content') or page.query_selector('img.global-nav__me-photo'):
            return True
        # Absence of login form fields
        if page.url and 'login' in page.url.lower():
            return False
    except Exception:
        return False
    return True

def collect_jobs(search: Dict[str, Any], limit: int = 30, user_data_dir: Optional[Path] = None, headless: bool = False, abort_if_login: bool = False):  # -> List[JobPosting]
    """Collect jobs for one search definition. Requires that you are already logged in (persistent profile)."""
    # Lazy import here to avoid slowing down module import when only helper
    # functions or dataclasses are needed.
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError  # type: ignore
    keywords = search.get('keywords', '')
    location = search.get('location', '')
    seniority = search.get('seniority')
    date_posted = search.get('date_posted')
    remote = search.get('remote')
    geo_id = search.get('geoId')  # user can supply if known
    raw_url = search.get('raw_url')

    logger = logging.getLogger('collector')
    url = raw_url if raw_url else build_search_url(keywords, location, date_posted, remote, seniority, geo_id)
    results: List[JobPosting] = []
    logger.info(f"Starting search: keywords='{keywords}' location='{location}' limit={limit} headless={headless}")
    log_event('search_start', keywords=keywords, location=location, limit=limit, headless=headless)

    profile_dir = str(user_data_dir) if user_data_dir else None

    diagnostics_dir = Path('scraper/data/diagnostics')
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(profile_dir or './data/browser_profile', headless=headless)
        except Exception as e:
            logger.error(f"Failed to launch browser context: {e}")
            log_event('error', stage='launch', message=str(e))
            return []
        secondary_location_scan = None  # init for static analyzers
        page = browser.new_page()
    # Factory closure for secondary location scan reused per job click
        secondary_location_scan = secondary_location_scan_factory(page)
        # Optional: capture console warnings for debugging with a safe handler
        def _console_handler(msg):
            try:
                mtype_attr = getattr(msg, 'type', None)
                if callable(mtype_attr):
                    mtype = mtype_attr()
                else:
                    mtype = mtype_attr or 'unknown'
                text_attr = getattr(msg, 'text', None)
                if callable(text_attr):
                    text_val = text_attr()
                else:
                    text_val = text_attr or ''
                logger.debug(f"PAGE_CONSOLE {mtype} {text_val[:300]}")
            except Exception:
                logger.debug("Failed handling console message", exc_info=True)
        try:
            page.on('console', _console_handler)
        except Exception:
            logger.debug("Could not register console handler", exc_info=True)
        if USER_AGENT_OVERRIDE:
            page.set_extra_http_headers({'User-Agent': USER_AGENT_OVERRIDE})
        logger.debug(f"Navigating to {url}")
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
        except PlaywrightTimeoutError:
            logger.error("Navigation timeout (initial load)")
            log_event('error', stage='navigate_initial', message='timeout')
            browser.close()
            return []
        polite_sleep(2.0, 3.5)
        # Login detection (early abort)
        if not _is_logged_in(page):
            if abort_if_login:
                logger.warning("Not logged in; aborting (abort_if_login=True)")
                log_event('login_abort_early')
                browser.close()
                return []
            logger.warning("Not logged in; waiting for manual authentication (up to 5m)")
            log_event('login_wait_start')
            remaining = 300
            while remaining > 0 and (not _is_logged_in(page)):
                time.sleep(5)
                remaining -= 5
            if not _is_logged_in(page):
                logger.error("Login not completed; aborting")
                log_event('error', stage='login_wait', message='timeout')
                browser.close()
                return []
            logger.info("Login completed; proceeding")
            log_event('login_wait_complete')

        # If redirected to login, wait for user to complete authentication.
        login_wait_seconds = 300  # max 5 minutes for manual / 2FA
        if 'login' in page.url.lower():
            if abort_if_login:
                logger.warning("Login required; aborting early due to abort_if_login=True")
                log_event('login_abort')
                browser.close()
                return []
            logger.warning("Login page detected. Please complete login in the opened browser window (up to 5 minutes)...")
            log_event('login_wait_start')
            while login_wait_seconds > 0 and 'login' in page.url.lower():
                time.sleep(5)
                login_wait_seconds -= 5
            if 'login' in page.url.lower():
                logger.error("Login not completed within timeout.")
                log_event('error', stage='login_wait', message='timeout')
                browser.close()
                return []
            logger.info("Login completed; proceeding with collection.")
            log_event('login_wait_complete')

        # Additional wait for results container to appear
        # Pre-scroll a bit to trigger lazy load
        for _ in range(3):
            try:
                page.mouse.wheel(0, 1200)
            except Exception:
                pass
            polite_sleep(0.8, 1.2)

        # Expanded set of selectors for job cards (include generic occludable variant seen in diagnostics)
        card_selector_union = ', '.join([
            'li.jobs-search-results__list-item',
            'div.jobs-search-results__list-item',
            'div.job-search-card',
            'li.jobs-search-results-list__list-item',
            'li.jobs-search-results__job-card-search--generic-occludable-area'
        ])
        try:
            page.wait_for_selector(card_selector_union, timeout=30000)
        except PlaywrightTimeoutError:
            logger.warning("No job result cards appeared after 30s; capturing early diagnostics.")
            log_event('warn', stage='wait_results', message='no_cards_initial')
            # Save early html for debugging before continuing
            try:
                early = diagnostics_dir / f"early_no_cards_{int(time.time())}.html"
                early.write_text(page.content(), encoding='utf-8')
                log_event('diagnostics_saved', html=str(early))
            except Exception:
                pass

        seen_ids = set()
        scroll_attempts = 0
        start_time = time.time()
        # Helper: fallback extraction by directly opening job detail page (if panel extraction fails)
        def fallback_fetch_job(job_id: str) -> Optional[Dict[str, Any]]:
            detail_page = browser.new_page()
            detail_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
            try:
                detail_page.goto(detail_url, wait_until='domcontentloaded', timeout=45000)
                # Wait briefly for company anchor/top card if possible (non-fatal)
                try:
                    detail_page.wait_for_selector('a.topcard__org-name-link, a[href*="/company/"], div.topcard__flavor-row', timeout=5000)
                except Exception:
                    pass
                polite_sleep(1.0, 1.8)
                data = extract_job_from_panel(detail_page)
                data['detail_url'] = detail_url
                return data
            except PlaywrightTimeoutError:
                logger.debug(f"Timeout loading detail page {detail_url}")
                return None
            except Exception as e:
                logger.debug(f"Error loading detail page {detail_url}: {e}")
                return None
            finally:
                try:
                    detail_page.close()
                except Exception:
                    pass

        # Identify scroll container (virtualized list) if present
        scroll_container_selectors = [
            'div.jobs-search-results-list',
            'ul.scaffold-layout__list-container'
        ]
        def scroll_results_container():
            for sel in scroll_container_selectors:
                el = page.query_selector(sel)
                if el:
                    try:
                        el.evaluate("node => node.scrollBy(0, 1200)")
                        return True
                    except Exception:
                        pass
            # Fallback to page-level scroll
            try:
                page.mouse.wheel(0, 2000)
            except Exception:
                pass
            return False

        while len(results) < limit and scroll_attempts < 15:
            cards = []
            # Collect union of card nodes once per iteration (no short-circuit OR so we gather all variants)
            for sel in [
                'li.jobs-search-results__list-item',
                'div.jobs-search-results__list-item',
                'div.job-search-card',
                'li.jobs-search-results-list__list-item',
                'li.jobs-search-results__job-card-search--generic-occludable-area'
            ]:
                try:
                    found = page.query_selector_all(sel)
                    if found:
                        cards.extend(found)
                except Exception:
                    continue
            # De-duplicate elements (by id attribute if present, else the element handle identity via list order)
            unique_cards = []
            seen_card_ids = set()
            for c in cards:
                cid = c.get_attribute('id') or id(c)
                if cid in seen_card_ids:
                    continue
                seen_card_ids.add(cid)
                unique_cards.append(c)
            cards = unique_cards
            if not cards and scroll_attempts == 0:
                logger.debug("No cards found on first pass; scrolling pre-emptively.")
            for card in cards:
                job_id = (
                    card.get_attribute('data-occludable-job-id') or
                    card.get_attribute('data-job-id') or
                    card.get_attribute('data-id')
                )
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                try:
                    # Ensure visibility / trigger virtualization
                    try:
                        card.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    card.click()
                except Exception:
                    logger.debug("Failed to click job card", exc_info=False)
                    continue
                polite_sleep(1.0, 2.0)
                panel_data = extract_job_from_panel(page)
                try:
                    panel_data['page_title'] = page.title()
                except Exception:
                    pass
                # Retry pass: if location missing after initial extraction, attempt delayed re-read of primary description container
                if not panel_data.get('location'):
                    try:
                        first_delay = SETTINGS.location_retry_first_delay
                        time.sleep(first_delay)
                        prim = page.query_selector('div.job-details-jobs-unified-top-card__primary-description-container')
                        if prim:
                            spans = prim.query_selector_all('span span, span:not(:has(*))') or []
                            for sp in spans:
                                try:
                                    tx = (sp.inner_text() or '').strip()
                                except Exception:
                                    continue
                                if tx and (',' in tx or 'united states' in tx.lower()) and any(ch.isalpha() for ch in tx):
                                    panel_data['location'] = panel_data.get('location') or tx
                                lw = tx.lower()
                                if not panel_data.get('work_mode') and any(k in lw for k in ['remote','hybrid','on-site','onsite']):
                                    panel_data['work_mode'] = 'remote' if 'remote' in lw else ('hybrid' if 'hybrid' in lw else 'onsite')
                                    if panel_data.get('location'):
                                        break
                    except Exception:
                        pass
                # Second timed retry + diagnostics capture if still missing
                if (not panel_data.get('location') or not panel_data.get('work_mode')):
                    try:
                        second_delay = SETTINGS.location_retry_second_delay
                        time.sleep(second_delay)
                        loc2, mode2, tokens2 = secondary_location_scan(panel_data.get('location'), panel_data.get('work_mode'))
                        if loc2 and not panel_data.get('location'):
                            panel_data['location'] = loc2
                        if mode2 and not panel_data.get('work_mode'):
                            panel_data['work_mode'] = mode2
                        # Diagnostics only if still missing location
                        if not panel_data.get('location') and os.getenv('SCRAPER_CAPTURE_LOCATION_DIAGNOSTICS','1') != '0':
                            try:
                                diag_dir = Path('scraper/data/diagnostics/location')
                                diag_dir.mkdir(parents=True, exist_ok=True)
                                snippet_selectors = [
                                    'div.job-details-jobs-unified-top-card__primary-description-container',
                                    'div.job-details-jobs-unified-top-card__sticky-header-job-title + div'
                                ]
                                html_fragments = []
                                for sel in snippet_selectors:
                                    try:
                                        el = page.query_selector(sel)
                                        if el:
                                            frag = el.inner_html() or ''
                                            if frag:
                                                html_fragments.append(f'<!-- {sel} -->\n' + frag[:4000])
                                    except Exception:
                                        continue
                                diag_payload = {
                                    'tokens': tokens2,
                                    'title': panel_data.get('title'),
                                    'company': panel_data.get('company_name'),
                                    'work_mode': panel_data.get('work_mode'),
                                    'selectors_used': snippet_selectors,
                                }
                                ts = int(time.time()*1000)
                                (diag_dir / f"locmiss_{ts}.json").write_text(json.dumps(diag_payload, ensure_ascii=False, indent=2), encoding='utf-8')
                                if html_fragments:
                                    (diag_dir / f"locmiss_{ts}.html").write_text('\n\n'.join(html_fragments), encoding='utf-8')
                            except Exception:
                                pass
                    except Exception:
                        pass
                # Normalize location token simple cleanup
                if panel_data.get('location'):
                    loc = panel_data['location'].strip()
                    loc = re.sub(r'\s+Remote$', '', loc, flags=re.I)
                    panel_data['location'] = loc
                # Extract posted_at from time tag if not already
                if not panel_data.get('posted_at'):
                    try:
                        time_el = page.query_selector('time[datetime]')
                        if time_el:
                            dt_attr = time_el.get_attribute('datetime')
                            if dt_attr and re.match(r'\d{4}-\d{2}-\d{2}', dt_attr):
                                panel_data['posted_at'] = datetime.strptime(dt_attr, '%Y-%m-%d').date()
                    except Exception:
                        pass
                # If critical fields missing, try fallback detail page
                if not panel_data.get('title') or not panel_data.get('description_raw'):
                    logger.debug(f"Fallback detail fetch for job {job_id}")
                    fb = fallback_fetch_job(job_id)
                    if fb:
                        panel_data.update({k: v for k, v in fb.items() if v})
                        log_event('detail_fallback', job_id=job_id)
                # Lazy import JobPosting only when we actually instantiate records
                from .models import JobPosting  # type: ignore
                jp = JobPosting(
                    job_id=str(job_id),
                    title=panel_data.get('title') or 'Unknown',
                    company_name=panel_data.get('company_name') or 'Unknown',
                    page_title=panel_data.get('page_title'),
                    location=panel_data.get('location'),
                    posted_at=panel_data.get('posted_at'),
                    description_raw=panel_data.get('description_raw'),
                    description_clean=panel_data.get('description_clean'),
                    apply_method=panel_data.get('apply_method'),
                    offered_salary_min=panel_data.get('offered_salary_min'),
                    offered_salary_max=panel_data.get('offered_salary_max'),
                    offered_salary_currency=panel_data.get('offered_salary_currency'),
                    benefits=panel_data.get('benefits') or [],
                    employment_type=panel_data.get('employment_type'),
                    work_mode=panel_data.get('work_mode'),
                    seniority_level=panel_data.get('seniority_level'),
                    apply_url=panel_data.get('apply_url'),
                )
                results.append(jp)
                logger.info(f"Extracted job {job_id} {jp.company_name} - {jp.title}")
                log_event('job_extracted', job_id=job_id, company=jp.company_name, title=jp.title, salary_min=jp.offered_salary_min, salary_max=jp.offered_salary_max)
                if len(results) >= limit:
                    break
            # scroll container to load more
            scrolled_inside = scroll_results_container()
            polite_sleep(1.2, 2.0)
            scroll_attempts += 1
            logger.debug(f"Scroll iteration {scroll_attempts}, scrolled_inside={scrolled_inside} collected={len(results)} seen={len(seen_ids)}")
        try:
            elapsed = round(time.time() - start_time, 2)
            logger.info(f"Completed search: collected={len(results)} elapsed={elapsed}s")
            log_event('search_complete', collected=len(results), elapsed_s=elapsed)
        except Exception as e:
            logger.error(f"Error finalizing search: {e}")
            log_event('error', stage='finalize', message=str(e))
        finally:
            # Diagnostics if zero results (potentially blocked or still not logged in)
            if len(results) == 0:
                try:
                    snap_html = diagnostics_dir / f"no_results_{int(time.time())}.html"
                    snap_png = diagnostics_dir / f"no_results_{int(time.time())}.png"
                    page.content() and snap_html.write_text(page.content(), encoding='utf-8')
                    page.screenshot(path=str(snap_png))
                    logger.info(f"Saved diagnostics: {snap_html.name}, {snap_png.name}")
                    log_event('diagnostics_saved', html=str(snap_html), screenshot=str(snap_png))
                except Exception:
                    logger.debug("Failed to save diagnostics", exc_info=True)
            browser.close()
    return results
