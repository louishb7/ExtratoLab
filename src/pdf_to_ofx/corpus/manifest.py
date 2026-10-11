"""Versioned local metadata, never copied into diagnostic reports."""

from dataclasses import dataclass, fields
from enum import StrEnum
import re
from typing import Self


class SourceKind(StrEnum):
    OFFICIAL_STANDARD = "official_standard"
    OFFICIAL_BANK = "official_bank"
    OFFICIAL_REGULATOR = "official_regulator"
    PUBLIC_EXAMPLE = "public_example"
    COMMUNITY_EXAMPLE = "community_example"
    PRIVATE_ACCEPTANCE = "private_acceptance"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    schema_version: int = 1
    corpus_id: str | None = None
    local_path: str | None = None
    sha256: str | None = None
    source_url: str | None = None
    source_kind: SourceKind | None = None
    institution: str | None = None
    country: str | None = None
    region: str | None = None
    document_kind: str | None = None
    language: str | None = None
    public_or_private: str | None = None
    retrieved_at: str | None = None
    notes: str | None = None

    authorization: str | None = None
    usage_conditions: str | None = None
    observed_features: tuple[str, ...] = ()
    evidence_kind: str | None = None
    validation_status: str | None = None
    dataset: str | None = None
    structural_family: str | None = None
    ground_truth_path: str | None = None

    @classmethod
    def from_dict(cls, value: object) -> Self:
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ValueError("Invalid manifest schema.")
        version = value.get("schema_version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("Unsupported manifest version.")
        research = {"authorization", "usage_conditions", "observed_features", "evidence_kind",
                    "validation_status", "dataset", "structural_family", "ground_truth_path"}
        if version == 1 and value.keys() & research:
            raise ValueError("Research metadata requires manifest version 2.")
        for key, item in value.items():
            if key == "observed_features":
                if not isinstance(item, list) or any(not isinstance(x, str) or not x.strip() for x in item):
                    raise ValueError("Invalid observed features.")
                for feature in item:
                    feature.encode("utf-8")
                continue
            if key != "schema_version" and item is not None and not isinstance(item, str):
                raise ValueError("Manifest metadata must be text or null.")
            if isinstance(item, str):
                item.encode("utf-8")
        # Validate types before set membership: malformed JSON arrays/objects
        # must become a per-row manifest error, never abort the entire batch.
        if version == 2 and value.get("dataset") not in {"development", "evaluation"}:
            raise ValueError("A research manifest requires an explicit dataset.")
        data = dict(value)
        if "observed_features" in data:
            data["observed_features"] = tuple(data["observed_features"])
        if data.get("sha256") is not None:
            if not re.fullmatch(r"[0-9a-fA-F]{64}", data["sha256"]):
                raise ValueError("Invalid manifest hash.")
            data["sha256"] = data["sha256"].lower()
        if data.get("source_kind") is not None:
            data["source_kind"] = SourceKind(data["source_kind"])
        if data.get("public_or_private") not in (None, "public", "private"):
            raise ValueError("Invalid visibility classification.")
        return cls(**data)
