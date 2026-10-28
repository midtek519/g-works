"""Read-only archive inventory and verified copying for recommendation letters.

This module never deletes or edits an archive original.  Inventory results and
extracted letter text can contain private information: callers must keep them
local and must not log or send them to an AI service automatically.
"""
from __future__ import annotations

from collections import defaultdict
import contextlib
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


DEFAULT_EXCLUDES = ("tools", "Students", "App", "runtime")
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SIGNED = re.compile(r"(?:^|[\s_\-(])signed(?:$|[\s_\-)])", re.I)
_SIGNED_END = re.compile(r"(?:[\s_\-]+signed|\s*\(signed\))\s*$", re.I)
_IDENTITY_MARKERS = re.compile(
    r"\s*(?:\s[-–—]\s|_)\s*(?:letterhead|recommendation(?:\s+letter)?|"
    r"letter(?:\s+of\s+recommendation)?)(?=$|[\s_\-(])", re.I
)
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def _linked(path: Path) -> bool:
    # NTFS junctions can lead outside an archive just as symbolic links can.
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(value: str, prefix: str = "F") -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def _candidate(path: Path) -> tuple[str, bool, str]:
    """Return a tentative filename label, never an established student identity."""
    label = _SIGNED_END.sub("", path.stem).strip(" _-–—")
    marker = _IDENTITY_MARKERS.search(label)
    if marker:
        label = label[:marker.start()].strip(" _-–—")
    label = label or path.stem
    tokens = _normalized(label).split()
    generic = {"letter", "letterhead", "recommendation", "template", "signed", "final", "draft"}
    sufficiently_specific = len(tokens) >= 2 and not all(t in generic for t in tokens)
    reason = ("matching_filename_stem" if sufficiently_specific
              else "matching_document_stem_requires_identity_review")
    return label, sufficiently_specific, reason


def audit_archive(root, exclude_dirs=DEFAULT_EXCLUDES) -> dict:
    """Hash local files and produce cautious, review-only grouping suggestions.

    ``path`` values are relative POSIX paths below ``root``; ``id`` is stable for
    that relative path. ``signed`` means an explicit signed marker in a PDF's
    filename, not verification of a visible signature. Groups are tentative and
    never merge different document families merely for sharing one name token.
    A one-token candidate can group matching complete document stems (including
    program/purpose), solely as versions needing explicit identity review.
    Exact duplicates are recorded, never removed. Symlinks are not followed.
    """
    base = Path(root).absolute()
    if _linked(base):
        raise ValueError("The archive root must not be a symbolic link.")
    base = base.resolve(strict=True)
    if not base.is_dir():
        raise ValueError("The archive root must be a directory.")
    excluded_names = {str(name).casefold() for name in exclude_dirs}
    files, errors = [], []
    excluded_temp = excluded_symlinks = excluded_directories = 0

    def walk(directory):
        nonlocal excluded_temp, excluded_symlinks, excluded_directories
        try:
            with os.scandir(directory) as scan:
                entries = sorted(list(scan), key=lambda e: (e.name.casefold(), e.name))
        except OSError as exc:
            errors.append({"path": Path(directory).relative_to(base).as_posix(),
                           "error": type(exc).__name__})
            return
        for entry in entries:
            relative = Path(entry.path).relative_to(base).as_posix()
            try:
                if entry.is_symlink() or _linked(Path(entry.path)):
                    excluded_symlinks += 1
                elif entry.is_dir(follow_symlinks=False):
                    if entry.name.casefold() in excluded_names:
                        excluded_directories += 1
                    else:
                        walk(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    if entry.name.startswith("~$"):
                        excluded_temp += 1
                        continue
                    path = Path(entry.path)
                    label, specific, reason = _candidate(path)
                    # Include the containing directory: same-named files in
                    # separate archive branches do not establish one identity.
                    document_stem = _SIGNED_END.sub("", path.stem).strip(" _-–—")
                    key = (path.parent.relative_to(base).as_posix() + "/"
                           + _normalized(label if specific else document_stem))
                    file_id = _stable_id(relative)
                    group_id = _stable_id(key, "G")
                    files.append({
                        "id": file_id, "path": relative, "display_name": entry.name,
                        "extension": path.suffix.lower(), "sha256": _hash(path),
                        "bytes": path.stat().st_size,
                        "signed": path.suffix.lower() == ".pdf" and bool(_SIGNED.search(path.stem)),
                        "group_id": group_id, "duplicate_of": None, "status": "original",
                        "tentative_label": label, "group_reason": reason,
                    })
            except OSError as exc:
                errors.append({"path": relative, "error": type(exc).__name__})

    walk(base)
    files.sort(key=lambda item: (item["path"].casefold(), item["path"]))
    hashes, grouped = {}, defaultdict(list)
    for item in files:
        if item["sha256"] in hashes:
            item["duplicate_of"] = hashes[item["sha256"]]
            item["status"] = "exact_duplicate"
        else:
            hashes[item["sha256"]] = item["id"]
        grouped[item["group_id"]].append(item)
    groups = [{
        "id": group_id, "label": items[0]["tentative_label"], "tentative": True,
        "files": [item["id"] for item in items],
        "match_reason": items[0]["group_reason"],
    } for group_id, items in grouped.items()]
    groups.sort(key=lambda group: (group["label"].casefold(), group["id"]))
    return {"root": str(base), "files": files, "groups": groups, "errors": errors,
            "summary": {"files": len(files), "signed_pdfs": sum(f["signed"] for f in files),
                        "duplicates": sum(f["duplicate_of"] is not None for f in files),
                        "groups": len(groups), "bytes": sum(f["bytes"] for f in files),
                        "excluded_temp": excluded_temp, "excluded_symlinks": excluded_symlinks,
                        "excluded_directories": excluded_directories, "errors": len(errors)}}


def _docx_text(path: Path) -> tuple[str, list[str]]:
    flags = ["Review the salutation, letterhead, date, and closing before saving the body."]
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if any("vbaproject" in name.casefold() for name in names):
            flags.append("Embedded active content was ignored; no macros were run.")
        if any(re.match(r"word/(header|footer)\d*\.xml$", name) for name in names):
            flags.append("Page headers and footers were not imported.")
        entry = archive.getinfo("word/document.xml")
        if entry.file_size > 12 * 1024 * 1024:
            raise ValueError("The document is too large for safe text extraction.")
        xml = archive.read(entry)
    # DOCX body text needs no relationship resolution, embedded objects, or
    # external resources. Reject DTDs rather than permit entity expansion.
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("Document XML with entity declarations is unsupported.")
    document = ET.fromstring(xml)
    paragraphs = []
    for paragraph in document.iter(_WORD_NS + "p"):
        pieces = []
        for element in paragraph.iter():
            if element.tag == _WORD_NS + "t":
                pieces.append(element.text or "")
            elif element.tag == _WORD_NS + "tab":
                pieces.append("\t")
            elif element.tag in {_WORD_NS + "br", _WORD_NS + "cr"}:
                pieces.append("\n")
        paragraphs.append("".join(pieces))
    return "\n\n".join(paragraphs).strip(), flags


def _pdf_text(path: Path) -> tuple[str, list[str]]:
    flags = ["PDF text may have altered line breaks; compare it with the signed original.",
             "Review the salutation, letterhead, date, and closing before saving the body."]
    try:
        from pypdf import PdfReader
        # Some PDF parsers print malformed-object diagnostics. Keep those in
        # local memory so no private document fragments reach a terminal log.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                flags.append("The PDF is encrypted and was not decrypted.")
                return "", flags
            if len(reader.pages) > 1000:
                raise ValueError("The PDF has too many pages for text extraction.")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if text:
            return text, flags
    except ImportError:
        pass
    except Exception:
        # Never propagate an extractor exception which might include private
        # document content in a caller's log. Try the installed local utility.
        flags.append("The first local PDF extractor could not read this document.")
    executable = shutil.which("pdftotext")
    if executable:
        try:
            result = subprocess.run(
                [executable, "-layout", "-enc", "UTF-8", str(path), "-"],
                capture_output=True, timeout=45, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                text = result.stdout.decode("utf-8", errors="replace").replace("\f", "\n\n").strip()
                if text:
                    return text, flags
        except (OSError, subprocess.TimeoutExpired):
            flags.append("The installed local PDF text utility could not read this document.")
    flags.append("No editable text was extracted. A scanned PDF may need local OCR or manual transcription.")
    return "", flags


def extract_editable_letter(path) -> dict:
    """Extract local text without rewriting or silently removing any body wording.

    The returned text is private. No print, network, OCR service, macro, or
    external link is used. The caller must present it for review before approval.
    """
    source = Path(path)
    if _linked(source) or not source.is_file():
        raise ValueError("Choose a regular local file for extraction.")
    extension = source.suffix.lower()
    if source.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("The letter is too large for local text extraction.")
    if extension == ".docx":
        text, flags = _docx_text(source)
    elif extension == ".pdf":
        text, flags = _pdf_text(source)
    elif extension == ".txt":
        text = source.read_text(encoding="utf-8-sig")
        flags = ["Review the salutation, letterhead, date, and closing before saving the body."]
    else:
        text, flags = "", ["This format needs manual transcription or conversion in a local application."]
    if not text and extension != ".pdf":
        flags.append("No editable letter text was extracted.")
    return {"text": text, "source_format": extension.lstrip("."),
            "flags": flags, "requires_review": True}


def _safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).rstrip(" .")
    if not value or value in {".", ".."}:
        raise ValueError("The destination filename is invalid.")
    path = Path(value)
    stem, suffix = path.stem, path.suffix
    if stem.upper() in _RESERVED:
        stem = "_" + stem
    suffix = suffix[:20]
    return stem[: max(1, 180 - len(suffix))] + suffix


def copy_to_student(file, root, student_root) -> dict:
    """Copy one inventoried original into a student folder and verify its bytes.

    Existing differing files are never overwritten. The source must resolve
    inside ``root``; destination is exactly one safe basename in student_root.
    No original or duplicate is deleted. ``file`` may be a file record or a path.
    """
    base = Path(root).resolve(strict=True)
    reference = file.get("path") if isinstance(file, dict) else file
    if reference is None:
        raise ValueError("A source path is required.")
    candidate = Path(reference)
    source = candidate if candidate.is_absolute() else base / candidate
    if _linked(source):
        raise ValueError("Symbolic-link sources are not copied.")
    source = source.resolve(strict=True)
    if not source.is_relative_to(base) or not source.is_file():
        raise ValueError("The source must be a file inside the archive.")
    source_hash = _hash(source)
    if isinstance(file, dict) and file.get("sha256") and file["sha256"] != source_hash:
        raise ValueError("The source changed after inventory; audit it again before copying.")
    destination_root = Path(student_root).absolute()
    if _linked(destination_root):
        raise ValueError("The destination must not be a symbolic link.")
    destination_root.mkdir(parents=True, exist_ok=True)
    destination_root = destination_root.resolve(strict=True)
    safe_name = _safe_filename(source.name)
    destination = destination_root / safe_name
    if destination.resolve(strict=False).parent != destination_root:
        raise ValueError("The destination filename leaves the student folder.")
    if _linked(destination):
        raise ValueError("The destination file must not be a symbolic link.")
    if destination.exists() and _hash(destination) != source_hash:
        named = Path(safe_name)
        for length in (8, 16, 32, 64):
            destination = destination_root / f"{named.stem}--{source_hash[:length]}{named.suffix}"
            if _linked(destination):
                raise ValueError("The destination file must not be a symbolic link.")
            if not destination.exists() or _hash(destination) == source_hash:
                break
        else:
            raise ValueError("No unused verified destination filename is available.")
    existed = destination.exists()
    if not existed:
        # Exclusive creation prevents accidentally replacing another file even
        # if something changes after the preceding collision check.
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
    if _hash(destination) != source_hash:
        raise ValueError("The copied file failed verification; the original is intact.")
    return {"path": str(destination), "sha256": source_hash,
            "bytes": destination.stat().st_size,
            "source_id": file.get("id") if isinstance(file, dict) else _stable_id(source.relative_to(base).as_posix()),
            "already_exists": existed}
