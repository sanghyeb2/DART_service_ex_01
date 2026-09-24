"""README의 JSON 계약. 빈 값은 허용하고 잘못된 타입/추가 필드는 거부한다."""

from pydantic import BaseModel, ConfigDict, Field


class ResultModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class SourceItem(ResultModel):
    source_page: int | None = Field(default=None, ge=1)


class MarketItem(SourceItem):
    topic: str = ''
    description: str = ''


class RiskItem(SourceItem):
    risk: str = ''
    description: str = ''


class BusinessResult(ResultModel):
    company_name: str = ''
    report_period: str = ''
    business_summary: str = ''
    business_segments: list[str] = Field(default_factory=list)
    major_products: list[str] = Field(default_factory=list)
    market_conditions: list[MarketItem] = Field(default_factory=list)
    market_outlook: list[MarketItem] = Field(default_factory=list)
    competitive_factors: list[str] = Field(default_factory=list)
    sales_strategy: list[str] = Field(default_factory=list)
    major_risks: list[RiskItem] = Field(default_factory=list)


class RDProject(SourceItem):
    project_name: str = ''
    technology: str = ''
    description: str = ''


class Investment(SourceItem):
    target: str = ''
    amount: str = ''
    purpose: str = ''
    status: str = ''


class Production(SourceItem):
    site: str = ''
    capacity: str = ''
    output: str = ''
    utilization: str = ''


class TechResult(ResultModel):
    # 문자열을 사용하면 보고서의 단위를 그대로 보존할 수 있다.
    revenue: str | float | None = None
    operating_profit: str | float | None = None
    rd_expense: str | float | None = None
    rd_focus: list[str] = Field(default_factory=list)
    rd_projects: list[RDProject] = Field(default_factory=list)
    major_investments: list[Investment] = Field(default_factory=list)
    production_status: list[Production] = Field(default_factory=list)
    new_business: list[str] = Field(default_factory=list)
    employee_count: int | None = Field(default=None, ge=0)
    employee_summary: str = ''
    technology_keywords: list[str] = Field(default_factory=list)


class Evidence(SourceItem):
    fact: str = ''


class InsightItem(ResultModel):
    description: str = ''
    evidence: list[Evidence] = Field(default_factory=list)


class JobInsight(ResultModel):
    job_area: str = ''
    reason: str = ''
    keywords: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class InsightResult(ResultModel):
    industry_trends: list[InsightItem] = Field(default_factory=list)
    company_strategy: list[InsightItem] = Field(default_factory=list)
    technology_focus: list[InsightItem] = Field(default_factory=list)
    investment_direction: list[InsightItem] = Field(default_factory=list)
    growth_signals: list[InsightItem] = Field(default_factory=list)
    risk_signals: list[InsightItem] = Field(default_factory=list)
    job_insights: list[JobInsight] = Field(default_factory=list)
    job_keywords: list[str] = Field(default_factory=list)
    interview_points: list[str] = Field(default_factory=list)
    summary: str = ''
