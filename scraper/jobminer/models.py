from __future__ import annotations
from datetime import datetime, date, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, field_validator, Field

class JobPosting(BaseModel):
    job_id: str
    title: str
    company_name: str
    page_title: Optional[str] = None  # raw browser page title for diagnostics / enrichment
    company_linkedin_id: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None  # remote | hybrid | onsite | unknown
    # Enrichment fields (added later; may be null if not yet enriched)
    company_name_normalized: Optional[str] = None  # canonical company (after mapping / cleaning)
    location_normalized: Optional[str] = None  # canonical city, region, country string
    location_meta: Optional[Dict[str, Any]] = None  # structured geocode pieces: city/state/country/lat/lon/source
    # Provenance / enrichment metadata
    company_map_key: Optional[str] = None  # raw key that matched mapping (lowered)
    normalization_version: Optional[str] = None  # version string for normalization logic
    enrichment_run_at: Optional[datetime] = None  # timestamp when enrichment last ran
    geocode_lat: Optional[float] = None
    geocode_lon: Optional[float] = None
    posted_at: Optional[date] = None
    collected_at: datetime = datetime.now(timezone.utc)
    employment_type: Optional[str] = None
    seniority_level: Optional[str] = None
    skills_extracted: List[str] = Field(default_factory=list)
    description_raw: Optional[str] = None
    description_clean: Optional[str] = None
    apply_method: Optional[str] = None  # linkedin_easy_apply | external | unknown
    apply_url: Optional[str] = None
    recruiter_profiles: List[str] = Field(default_factory=list)
    offered_salary_min: Optional[float] = None  # in annual USD equivalent if convertible
    offered_salary_max: Optional[float] = None
    offered_salary_currency: Optional[str] = None
    salary_period: Optional[str] = None  # yearly | monthly | day | hour (raw from source if available)
    salary_is_predicted: Optional[bool] = None  # True if provider marks salary as predicted / estimated
    benefits: List[str] = Field(default_factory=list)  # normalized benefit keywords
    score_total: Optional[float] = None
    score_breakdown: Optional[Dict[str, float]] = None
    status: str = "new"  # new | reviewed | shortlisted | applied | archived | duplicate
    skills_meta: Optional[Dict[str, Any]] = None  # sources & diagnostics
    provenance: List[str] = Field(default_factory=list)  # list of source names contributing this record

    @field_validator("skills_extracted", "recruiter_profiles", "benefits", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

class SkillProfile(BaseModel):
    resume_skills: List[str]
    expanded_skills: List[str]
    last_built: datetime = datetime.now(timezone.utc)

class ScoreWeights(BaseModel):
    skill: float
    semantic: float
    recency: float
    seniority: float
    company: float

class ScoreThresholds(BaseModel):
    shortlist: float
    review: float

class ScoredJob(BaseModel):
    job: JobPosting
    reason: Optional[str] = None
