import os
from pathlib import Path
import json

KB_CHUNK_DIR = Path("data/kb_chunks")
KB_CHUNK_MAX_BYTES = 450_000   # safely under Catalyst's 500KB per-upload limit

def _format_fir_document(fir: dict) -> str:
    """Formats a single FIR as a plain-text KB document.
    Only includes semantic content (narrative + MO) plus structured
    anchor fields (FIR_ID, DISTRICT, CRIME_TYPE) for cross-referencing.
    All other structured fields (IDs, dates, IPC sections, accused) belong
    in ZTSQL -- not the KB.
    """
    lines = [
        f"FIR_ID: {fir.get('fir_internal_id', '')}",
        f"DISTRICT: {fir.get('district_name', '')}",
    ]
    if fir.get('crime_sub_head_name'):
        lines.append(f"CRIME_TYPE: {fir.get('crime_sub_head_name')}")
    if fir.get('mo_descriptor'):
        lines.append(f"MO: {fir.get('mo_descriptor')}")
    if fir.get('narrative'):
        lines.append(f"NARRATIVE: {fir.get('narrative')}")
    return "\n".join(lines) + "\n\n---\n\n"

def generate_kb_upload_files(firs: list[dict]) -> list[Path]:
    """Chunks all FIR documents into files < KB_CHUNK_MAX_BYTES each.
    Returns the list of generated file paths.
    """
    KB_CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    chunk_index = 1
    current_chunk = []
    current_bytes = 0
    generated_files = []

    for fir in firs:
        doc = _format_fir_document(fir)
        doc_bytes = len(doc.encode("utf-8"))

        if current_bytes + doc_bytes > KB_CHUNK_MAX_BYTES and current_chunk:
            _write_chunk(current_chunk, chunk_index, generated_files)
            chunk_index += 1
            current_chunk = []
            current_bytes = 0

        current_chunk.append(doc)
        current_bytes += doc_bytes

    if current_chunk:
        _write_chunk(current_chunk, chunk_index, generated_files)

    print(f"[KB] Generated {len(generated_files)} upload file(s) in {KB_CHUNK_DIR}/")
    return generated_files

def _write_chunk(docs: list[str], index: int, paths: list[Path]) -> None:
    path = KB_CHUNK_DIR / f"kb_upload_chunk_{index:03d}.txt"
    path.write_text("".join(docs), encoding="utf-8")
    size_kb = path.stat().st_size / 1024
    print(f"[KB] Wrote {path.name} ({len(docs)} docs, {size_kb:.1f} KB)")
    paths.append(path)

async def upload_fir_to_kb(fir: dict):
    raise NotImplementedError(
        "upload_fir_to_kb() is disabled in v10. Use generate_kb_upload_files() "
        "to produce files for manual console upload. See Architecture v10 §20a."
    )
