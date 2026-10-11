"""Reproducible fictitious experiments and independent recipe expectations."""
import argparse
import hashlib
import json
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas


def generate(output: Path) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use a new or empty directory.")
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    cases = json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))
    for case in cases:
        path = output / (case["id"] + ".pdf")
        canvas = Canvas(str(path), pagesize=(595, 842), invariant=1, pageCompression=0)
        canvas.setTitle("ExtratoLab fictitious structural experiment")
        canvas.setAuthor("Synthetic data only")
        for page in case["pages"]:
            canvas.setFont("Helvetica", 9)
            for row in page:
                for x, text in row["cells"]:
                    canvas.drawString(x, 842-row["y"], text)
            canvas.showPage()
        canvas.save()
        truth = dict(schema_version=1, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     independently_verified=True, evidence_kind="synthetic_recipe", expectation=case["expectation"])
        if case["statement"] is not None:
            truth["statement"] = case["statement"]
        truth_path = output / (case["id"] + ".truth.json")
        truth_path.write_text(json.dumps(truth,sort_keys=True,ensure_ascii=True)+"\n",encoding="utf-8")
        entries.append(dict(schema_version=2,corpus_id=case["id"],local_path=path.name,sha256=truth["sha256"],
                            source_kind="synthetic",public_or_private="public",country=case["country"],
                            language=case["language"],document_kind="bank_statement",dataset=case["dataset"],
                            authorization="Fictitious recipe maintained in the repository",
                            usage_conditions="Test and research only; no real institution coverage claim",
                            evidence_kind="synthetic_recipe",validation_status="recipe_reviewed",
                            observed_features=case["features"],structural_family=case["id"],ground_truth_path=truth_path.name))
    manifest = output/"corpus.jsonl"
    manifest.write_text("".join(json.dumps(e,sort_keys=True,ensure_ascii=True)+"\n" for e in entries),encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    generate(parser.parse_args().output)
