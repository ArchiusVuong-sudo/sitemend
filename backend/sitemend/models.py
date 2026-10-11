"""Data model.

Site -> Page / SearchStat (synthetic search data)
Run (scan, generate, deploy, verify) -> Issue (per scan), Span (trace)
Fix -> FixAttempt (each try at the text, with its check results)
TextClaim reserves a title or description so parallel sessions never write the same one.
Release is an immutable snapshot of the fix operations served by the edge.
"""

from __future__ import annotations

from django.db import models


class Category(models.TextChoices):
    TECHNICAL = "technical", "Technical"
    TITLES = "titles", "Titles"
    META = "meta", "Meta descriptions"
    ALT = "alt", "Alt text"
    RICH = "rich", "Rich results"


class Severity(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class Site(models.Model):
    name = models.CharField(max_length=120)
    domain = models.CharField(max_length=200)
    custom_instructions = models.TextField(blank=True, default="")
    never_use_words = models.JSONField(default=list, blank=True)
    active_release = models.ForeignKey(
        "Release", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Page(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="pages")
    path = models.CharField(max_length=300)
    title = models.CharField(max_length=500, blank=True, default="")
    meta_description = models.TextField(blank=True, default="")
    html = models.TextField(blank=True, default="")  # origin HTML as of the latest scan
    status_code = models.IntegerField(default=200)
    last_run = models.ForeignKey("Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["site", "path"], name="page_unique_path")]
        ordering = ["path"]


class SearchStat(models.Model):
    """Synthetic 28-day search performance for one page."""

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="search_stats")
    path = models.CharField(max_length=300)
    impressions = models.IntegerField()
    clicks = models.IntegerField()
    ctr = models.FloatField()
    position = models.FloatField()
    queries = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["site", "path"], name="stat_unique_path")]

    @property
    def top_query(self) -> str:
        return self.queries[0]["query"] if self.queries else ""


class Policy(models.Model):
    class Mode(models.TextChoices):
        AUTOPILOT = "autopilot", "Autopilot"
        APPROVAL = "approval", "Approval"
        OFF = "off", "Off"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="policies")
    category = models.CharField(max_length=20, choices=Category.choices)
    mode = models.CharField(max_length=20, choices=Mode.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["site", "category"], name="policy_unique_category")]


class Run(models.Model):
    class Kind(models.TextChoices):
        SCAN = "scan", "Scan"
        GENERATE = "generate", "Generate fixes"
        DEPLOY = "deploy", "Deploy"
        VERIFY = "verify", "Verify"
        REVERT = "revert", "Revert"
        ROLLBACK = "rollback", "Rollback"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="runs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    target = models.CharField(max_length=10, default="origin")  # origin or edge
    total = models.IntegerField(default=0)
    done = models.IntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    release = models.ForeignKey("Release", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    llm_mode = models.CharField(max_length=10, blank=True, default="")
    finalized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class Issue(models.Model):
    """One finding of one scan. The fingerprint (path, rule, key) is stable across scans."""

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="issues")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="issues")
    path = models.CharField(max_length=300)
    rule = models.CharField(max_length=40)
    key = models.CharField(max_length=300, blank=True, default="")
    category = models.CharField(max_length=20, choices=Category.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    message = models.CharField(max_length=300)
    evidence = models.TextField(blank=True, default="")
    priority = models.FloatField(default=0)
    priority_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["-priority", "path", "rule", "key"]
        constraints = [
            models.UniqueConstraint(fields=["run", "path", "rule", "key"], name="issue_unique_in_run")
        ]

    @property
    def fingerprint(self) -> str:
        return f"{self.path}|{self.rule}|{self.key}"


class Fix(models.Model):
    class Source(models.TextChoices):
        RULE = "rule", "Rule"
        MODEL = "model", "Model"

    class Status(models.TextChoices):
        WRITING = "writing", "Writing"
        NEEDS_REVIEW = "needs_review", "Needs review"
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        LIVE = "live", "Deployed"
        VERIFIED = "verified", "Verified live"
        REVERTED = "reverted", "Reverted"

    class Confidence(models.TextChoices):
        HIGH = "high", "High"
        LOW = "low", "Low"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="fixes")
    path = models.CharField(max_length=300)
    category = models.CharField(max_length=20, choices=Category.choices)
    kind = models.CharField(max_length=40)  # operation name, for example set_title
    target = models.CharField(max_length=300, blank=True, default="")  # image src or link href
    rules = models.JSONField(default=list)  # issue rules this fix addresses
    source = models.CharField(max_length=10, choices=Source.choices)
    before = models.TextField(blank=True, default="")
    after = models.TextField(blank=True, default="")
    op = models.JSONField(default=dict)  # what the edge applies
    status = models.CharField(max_length=20, choices=Status.choices)
    confidence = models.CharField(max_length=10, choices=Confidence.choices, default=Confidence.HIGH)
    confidence_note = models.CharField(max_length=300, blank=True, default="")
    checks = models.JSONField(default=list)  # result of the latest check run
    approved_by = models.CharField(max_length=20, blank=True, default="")  # autopilot or reviewer
    error = models.TextField(blank=True, default="")
    created_run = models.ForeignKey(Run, null=True, on_delete=models.SET_NULL, related_name="fixes")
    verified_run = models.ForeignKey(Run, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "path", "kind", "target"]
        constraints = [
            models.UniqueConstraint(fields=["site", "path", "kind", "target"], name="fix_unique_target")
        ]

    @property
    def checks_passed(self) -> bool:
        return all(c.get("passed") for c in self.checks)


class FixAttempt(models.Model):
    class Source(models.TextChoices):
        MODEL = "model", "Model"
        REPLAY = "replay", "Replay"
        REVIEWER = "reviewer", "Reviewer"

    fix = models.ForeignKey(Fix, on_delete=models.CASCADE, related_name="attempts")
    number = models.IntegerField()
    source = models.CharField(max_length=10, choices=Source.choices)
    text = models.TextField()
    passed = models.BooleanField(default=False)
    checks = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]


class ModelSession(models.Model):
    """One model session for one page, with its cost and latency."""

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="sessions")
    path = models.CharField(max_length=300)
    mode = models.CharField(max_length=10)  # live or replay
    model = models.CharField(max_length=60)
    latency_ms = models.IntegerField(default=0)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cost_usd = models.FloatField(null=True, blank=True)
    turns = models.IntegerField(default=0)
    retries = models.IntegerField(default=0)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class TextClaim(models.Model):
    """Reserves a normalized title or description for one fix.

    The unique constraint is what keeps parallel sessions from shipping the
    same title on two pages: the second insert fails inside its transaction.
    """

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="+")
    field = models.CharField(max_length=20)
    norm_text = models.CharField(max_length=400)
    fix = models.ForeignKey(Fix, on_delete=models.CASCADE, related_name="claims")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "field", "norm_text"], name="claim_unique_text"),
            models.UniqueConstraint(fields=["fix"], name="claim_one_per_fix"),
        ]


class Release(models.Model):
    class Kind(models.TextChoices):
        AUTOPILOT = "autopilot", "Autopilot"
        DEPLOY = "deploy", "Deploy"
        REVERT = "revert", "Revert"
        ROLLBACK = "rollback", "Rollback"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="releases")
    number = models.IntegerField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    note = models.CharField(max_length=300, blank=True, default="")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ops = models.JSONField(default=list)  # [{"fix_id", "path", "op"}], sorted, never edited
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["site", "number"], name="release_unique_number")]

    @property
    def label(self) -> str:
        return f"v{self.number}"

    @property
    def fix_ids(self) -> list[int]:
        return [o["fix_id"] for o in self.ops]


class Span(models.Model):
    """One traced step: a Celery task, a page fetch, a model session or a tool call."""

    class Kind(models.TextChoices):
        TASK = "task", "Task"
        FETCH = "fetch", "Page fetch"
        MODEL = "model", "Model session"
        TOOL = "tool", "Tool call"
        STEP = "step", "Step"

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="spans")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    label = models.CharField(max_length=300, blank=True, default="")
    started_at = models.DateTimeField()
    duration_ms = models.FloatField(default=0)
    status = models.CharField(max_length=10, default="ok")  # ok or error
    retries = models.IntegerField(default=0)
    error = models.TextField(blank=True, default="")
    attrs = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["started_at", "id"]
