from __future__ import annotations

from rest_framework import serializers

from ..models import Category, Fix, FixAttempt, Issue, ModelSession, Policy, Release, Run, Span


class RunSerializer(serializers.ModelSerializer):
    release = serializers.SerializerMethodField()
    duration_ms = serializers.SerializerMethodField()

    class Meta:
        model = Run
        fields = ["id", "kind", "status", "target", "total", "done", "summary", "error", "release", "llm_mode",
                  "created_at", "started_at", "finished_at", "duration_ms"]

    def get_release(self, run: Run) -> str | None:
        return run.release.label if run.release_id and run.release else None

    def get_duration_ms(self, run: Run) -> int | None:
        if run.started_at and run.finished_at:
            return round((run.finished_at - run.started_at).total_seconds() * 1000)
        return None


class SpanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Span
        fields = ["id", "parent", "name", "kind", "label", "started_at", "duration_ms", "status", "retries",
                  "error", "attrs"]


class IssueSerializer(serializers.ModelSerializer):
    fingerprint = serializers.CharField(read_only=True)

    class Meta:
        model = Issue
        fields = ["id", "path", "rule", "key", "category", "severity", "message", "evidence", "priority",
                  "priority_reason", "fingerprint"]


class AttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = FixAttempt
        fields = ["number", "source", "text", "passed", "checks", "created_at"]


class FixSerializer(serializers.ModelSerializer):
    checks_passed = serializers.BooleanField(read_only=True)
    attempts_count = serializers.IntegerField(source="attempts.count", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Fix
        fields = ["id", "path", "category", "kind", "target", "rules", "source", "before", "after", "op", "status",
                  "status_label", "confidence", "confidence_note", "checks", "checks_passed", "approved_by", "error",
                  "attempts_count", "created_run", "verified_run", "updated_at"]


class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelSession
        fields = ["path", "mode", "model", "latency_ms", "input_tokens", "output_tokens", "cost_usd", "turns",
                  "retries", "error", "created_at"]


class ReleaseSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)
    parent_label = serializers.SerializerMethodField()

    class Meta:
        model = Release
        fields = ["id", "number", "label", "kind", "note", "parent_label", "ops", "created_at"]

    def get_parent_label(self, release: Release) -> str | None:
        return release.parent.label if release.parent_id and release.parent else None


# ----- inputs -------------------------------------------------------------------------------------------


class SiteSettingsInput(serializers.Serializer):
    custom_instructions = serializers.CharField(max_length=2000, allow_blank=True, required=False, trim_whitespace=True)
    never_use_words = serializers.ListField(
        child=serializers.CharField(max_length=60, trim_whitespace=True), max_length=50, required=False)

    def validate_never_use_words(self, words: list[str]) -> list[str]:
        seen: list[str] = []
        for w in words:
            w = w.strip().lower()
            if w and w not in seen:
                seen.append(w)
        return seen


class PolicyInput(serializers.Serializer):
    mode = serializers.ChoiceField(choices=Policy.Mode.choices)


class TextInput(serializers.Serializer):
    text = serializers.CharField(max_length=400, trim_whitespace=True)


class CategoryInput(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.choices)
