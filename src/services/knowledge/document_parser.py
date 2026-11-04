import html
import importlib.util
import inspect
import json
import os
import re
import shlex
import signal
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import fitz

from src.config import Config


PARSER_OUTPUT_SCHEMA_VERSION = getattr(Config, "PARSER_OUTPUT_SCHEMA_VERSION", "adaptive_pdf_parse_v1")


@dataclass
class ParsedSection:
    text: str
    page: Optional[int] = None
    chapter: str = ""
    section: str = ""
    location: str = ""
    spine_index: Optional[int] = None
    href: str = ""
    paragraph_index: Optional[int] = None


@dataclass
class ParsedDocument:
    file_path: str
    parser_type: str
    parser_version: str
    extraction_status: str
    extraction_quality: float
    sections: List[ParsedSection] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata_hints: Dict[str, Any] = field(default_factory=dict)

    @property
    def extracted_char_count(self) -> int:
        return sum(len(section.text or "") for section in self.sections)

    @property
    def extracted_word_count(self) -> int:
        return sum(len((section.text or "").split()) for section in self.sections)

    @property
    def text(self) -> str:
        return "\n\n".join(section.text.strip() for section in self.sections if (section.text or "").strip())

    @property
    def parser_id(self) -> str:
        return self.parser_type

    @property
    def quality(self) -> Dict[str, Any]:
        hints = self.metadata_hints or {}
        quality = dict(hints.get("quality") or {})
        quality.setdefault("total_chars", self.extracted_char_count)
        quality.setdefault("total_words", self.extracted_word_count)
        quality.setdefault("quality_score", self.extraction_quality)
        quality.setdefault("needs_ocr", self.extraction_status == "NEEDS_OCR")
        return quality


@dataclass
class PageProbeResult:
    page_number: int
    human_page_number: int
    chars: int
    words: int
    image_count: int
    image_area_ratio: float
    table_count: int
    table_like_ratio: float
    empty_text: bool
    low_text_density: bool
    likely_chart_or_figure_caption: bool
    likely_table_caption: bool
    likely_scan_or_ocr_page: bool
    multi_column_likelihood: bool
    complexity_score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class PdfProbeResult:
    file_path: str
    total_pages: int
    total_chars: int
    total_words: int
    avg_chars_per_page: float
    empty_pages_count: int
    image_count: int
    image_count_per_page: List[int]
    table_count: int
    table_like_ratio: float
    scanned_likelihood: str
    needs_ocr: bool
    layout_complexity: str
    page_metrics: List[PageProbeResult] = field(default_factory=list)
    inferred_knowledge_type: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def complex_page_ratio(self) -> float:
        if not self.page_metrics:
            return 0.0
        complex_pages = [page for page in self.page_metrics if page.complexity_score >= 0.45]
        return len(complex_pages) / max(1, len(self.page_metrics))

    @property
    def selected_candidate_pages(self) -> List[int]:
        return [page.human_page_number for page in self.page_metrics if page.complexity_score >= 0.45]


@dataclass
class ParsePlan:
    plan_type: str
    base_parser: str
    advanced_parser: str = ""
    selected_pages: List[int] = field(default_factory=list)
    selected_ranges: List[tuple[int, int]] = field(default_factory=list)
    reason: str = ""
    confidence: float = 1.0
    knowledge_type: str = ""
    probe_summary: Dict[str, Any] = field(default_factory=dict)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class DocumentParser:
    supported_extensions: set[str] = set()

    def parse(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> ParsedDocument:
        raise NotImplementedError


class PyMuPDFProbeService:
    def probe(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> PdfProbeResult:
        warnings: List[str] = []
        page_metrics: List[PageProbeResult] = []
        image_counts: List[int] = []
        total_chars = 0
        total_words = 0
        table_count = 0
        empty_pages = 0
        image_count = 0

        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            warnings.append(str(exc))
            return PdfProbeResult(
                file_path=file_path,
                total_pages=0,
                total_chars=0,
                total_words=0,
                avg_chars_per_page=0.0,
                empty_pages_count=0,
                image_count=0,
                image_count_per_page=[],
                table_count=0,
                table_like_ratio=0.0,
                scanned_likelihood="low",
                needs_ocr=False,
                layout_complexity="low",
                inferred_knowledge_type=_infer_knowledge_type(file_path, metadata),
                warnings=warnings,
            )

        total_pages = len(doc)
        for page_index in range(total_pages):
            page = doc[page_index]
            text = page.get_text() or ""
            chars = len(text.strip())
            words = len(text.split())
            page_images = len(page.get_images(full=True))
            image_area_ratio = _page_image_area_ratio(page)
            page_table_count = _estimate_table_like_blocks(text)
            page_table_like_ratio = _table_like_ratio(text)
            empty_text = chars == 0
            low_text_density = chars < int(getattr(Config, "MINERU_SELECTIVE_LOW_TEXT_CHARS", 300))
            figure_caption = _has_figure_caption(text)
            table_caption = _has_table_caption(text)
            scan_page = (empty_text or low_text_density) and (page_images > 0 or image_area_ratio >= 0.20)
            multi_column = _multi_column_likelihood(text)
            reasons: List[str] = []
            if low_text_density:
                reasons.append("low_text_density")
            if image_area_ratio >= float(getattr(Config, "MINERU_SELECTIVE_IMAGE_AREA_RATIO", 0.20)):
                reasons.append("large_image_area")
            if page_table_like_ratio >= float(getattr(Config, "MINERU_SELECTIVE_TABLE_LIKE_THRESHOLD", 0.25)):
                reasons.append("table_like")
            if figure_caption:
                reasons.append("figure_caption")
            if table_caption:
                reasons.append("table_caption")
            if scan_page:
                reasons.append("scan_or_ocr_page")
            if multi_column:
                reasons.append("multi_column")
            complexity_score = _page_complexity_score(
                low_text_density=low_text_density,
                image_area_ratio=image_area_ratio,
                table_like_ratio=page_table_like_ratio,
                figure_caption=figure_caption,
                table_caption=table_caption,
                scan_page=scan_page,
                multi_column=multi_column,
            )

            total_chars += chars
            total_words += words
            table_count += page_table_count
            image_count += page_images
            image_counts.append(page_images)
            if empty_text:
                empty_pages += 1
            page_metrics.append(
                PageProbeResult(
                    page_number=page_index,
                    human_page_number=page_index + 1,
                    chars=chars,
                    words=words,
                    image_count=page_images,
                    image_area_ratio=round(image_area_ratio, 4),
                    table_count=page_table_count,
                    table_like_ratio=round(page_table_like_ratio, 4),
                    empty_text=empty_text,
                    low_text_density=low_text_density,
                    likely_chart_or_figure_caption=figure_caption,
                    likely_table_caption=table_caption,
                    likely_scan_or_ocr_page=scan_page,
                    multi_column_likelihood=multi_column,
                    complexity_score=round(complexity_score, 4),
                    reasons=reasons,
                )
            )
        doc.close()

        avg_chars = total_chars / total_pages if total_pages else 0.0
        empty_ratio = empty_pages / max(1, total_pages)
        scan_ratio = len([page for page in page_metrics if page.likely_scan_or_ocr_page]) / max(1, total_pages)
        scanned_likelihood = "high" if empty_ratio >= 0.6 or scan_ratio >= 0.5 else "medium" if empty_ratio >= 0.2 or scan_ratio >= 0.2 else "low"
        needs_ocr = scanned_likelihood == "high" or (avg_chars < 120 and image_count > 0)
        complex_ratio = len([page for page in page_metrics if page.complexity_score >= 0.45]) / max(1, total_pages)
        layout_complexity = "high" if complex_ratio >= 0.35 else "medium" if complex_ratio >= 0.12 else "low"
        table_like_ratio = sum(page.table_like_ratio for page in page_metrics) / max(1, len(page_metrics))

        result = PdfProbeResult(
            file_path=file_path,
            total_pages=total_pages,
            total_chars=total_chars,
            total_words=total_words,
            avg_chars_per_page=round(avg_chars, 2),
            empty_pages_count=empty_pages,
            image_count=image_count,
            image_count_per_page=image_counts,
            table_count=table_count,
            table_like_ratio=round(table_like_ratio, 4),
            scanned_likelihood=scanned_likelihood,
            needs_ocr=needs_ocr,
            layout_complexity=layout_complexity,
            page_metrics=page_metrics,
            inferred_knowledge_type=_infer_knowledge_type(file_path, metadata),
            warnings=warnings,
        )
        print(
            "[PdfProbe] "
            f"file={file_path} pages={result.total_pages} chars={result.total_chars} "
            f"avg_chars_per_page={result.avg_chars_per_page} images={result.image_count} "
            f"table_like_ratio={result.table_like_ratio} scanned_likelihood={result.scanned_likelihood} "
            f"needs_ocr={str(result.needs_ocr).lower()}"
        )
        selected_preview = result.selected_candidate_pages[:10]
        top_reasons = _top_probe_reasons(result.page_metrics)
        print(f"[PageProbe] file={file_path} selected_candidate_pages={selected_preview} top_reasons={top_reasons}")
        return result


class PdfDocumentParser(DocumentParser):
    supported_extensions = {".pdf"}

    def parse(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> ParsedDocument:
        parser_version = f"PyMuPDF-{fitz.VersionBind}"
        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            parsed = ParsedDocument(
                file_path=file_path,
                parser_type="pdf:pymupdf",
                parser_version=parser_version,
                extraction_status="FAILED",
                extraction_quality=0.0,
                warnings=[str(exc)],
                metadata_hints=_pdf_quality_hints(
                    total_pages=0,
                    total_chars=0,
                    total_words=0,
                    empty_pages=0,
                    image_count=0,
                    table_count=0,
                    quality_score=0.0,
                    fallback_used=False,
                    fallback_reason="",
                ),
            )
            _log_pdf_quality(parsed)
            return parsed

        sections: List[ParsedSection] = []
        empty_pages = 0
        total_pages = len(doc)
        image_count = 0
        table_count = 0
        for page_index in range(total_pages):
            page = doc[page_index]
            text = page.get_text()
            page_images = len(page.get_images(full=True))
            image_count += page_images
            if not text.strip():
                empty_pages += 1
                continue
            table_count += _estimate_table_like_blocks(text)
            if page_images:
                text = (
                    text.rstrip()
                    + f"\n\n[Figure/Image placeholder: page {page_index + 1}, images={page_images}; no visual interpretation performed.]"
                )
            sections.append(
                ParsedSection(
                    text=_normalize_markdown_text(text),
                    page=page_index + 1,
                    location=f"page:{page_index + 1}",
                )
            )
        doc.close()

        if total_pages == 0 or empty_pages == total_pages:
            status = "EMPTY_DOCUMENT"
            quality = 0.0
        else:
            quality = (total_pages - empty_pages) / total_pages
            if quality < 0.2:
                status = "NEEDS_OCR"
                sections = []
            elif quality < 0.8:
                status = "PARTIAL_TEXT"
            else:
                status = "CHUNKED"

        parsed = ParsedDocument(
            file_path=file_path,
            parser_type="pdf:pymupdf",
            parser_version=parser_version,
            extraction_status=status,
            extraction_quality=quality,
            sections=sections,
            metadata_hints=_pdf_quality_hints(
                total_pages=total_pages,
                total_chars=sum(len(section.text or "") for section in sections),
                total_words=sum(len((section.text or "").split()) for section in sections),
                empty_pages=empty_pages,
                image_count=image_count,
                table_count=table_count,
                quality_score=quality,
                fallback_used=False,
                fallback_reason="",
            ),
        )
        _log_pdf_quality(parsed)
        return parsed


class MinerUUnavailable(RuntimeError):
    pass


class MinerUFailed(RuntimeError):
    def __init__(
        self,
        message: str,
        returncode: Optional[int] = None,
        stdout_tail: str = "",
        stderr_tail: str = "",
    ):
        super().__init__(message)
        self.returncode = returncode
        self.stdout_tail = stdout_tail
        self.stderr_tail = stderr_tail


class MinerUTimeout(MinerUFailed):
    def __init__(self, timeout_seconds: int, stdout_tail: str = "", stderr_tail: str = ""):
        super().__init__(
            f"MinerU timed out after {timeout_seconds}s",
            returncode=None,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
        )
        self.timeout_seconds = timeout_seconds


class MinerUPdfParser(DocumentParser):
    supported_extensions = {".pdf"}

    def __init__(
        self,
        command_name: Optional[str] = None,
        backend: Optional[str] = None,
        method: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.command_name = command_name or getattr(Config, "MINERU_COMMAND", "mineru")
        self.backend = backend or getattr(Config, "MINERU_BACKEND", "pipeline")
        self.method = method or getattr(Config, "MINERU_METHOD", "auto")
        self.timeout_seconds = int(timeout_seconds or getattr(Config, "MINERU_TIMEOUT_SECONDS", 1800))

    def parse(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> ParsedDocument:
        if not self.is_available():
            raise MinerUUnavailable("MinerU local package/CLI is not available.")

        with tempfile.TemporaryDirectory(prefix="mineru_parse_") as tmpdir:
            cmd = self._build_command(file_path, tmpdir)
            print(
                "[MinerUParser] "
                f"command=\"{_format_command_for_log(cmd)}\" "
                f"backend={self.backend} method={self.method} timeout={self.timeout_seconds}"
            )
            completed = self._run_command(cmd)
            if completed.returncode != 0:
                stdout_tail = _tail(completed.stdout)
                stderr_tail = _tail(completed.stderr)
                reason = stderr_tail or stdout_tail or f"exit_code={completed.returncode}"
                raise MinerUFailed(
                    reason,
                    returncode=completed.returncode,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                )

            artifact = self._find_output_artifact(Path(tmpdir))
            if artifact is None:
                raise MinerUFailed("MinerU completed but no Markdown/JSON output was found.")

            if artifact.suffix.lower() == ".md":
                parsed = self._parse_markdown_artifact(file_path, artifact)
            else:
                parsed = self._parse_json_artifact(file_path, artifact)

        print(
            f"[MinerUParser] status=ok file={file_path} "
            f"pages={parsed.metadata_hints.get('total_pages', 0)} "
            f"chars={parsed.extracted_char_count} output_dir={tmpdir}"
        )
        _log_pdf_quality(parsed)
        return parsed

    def _build_command(self, file_path: str, output_dir: str) -> List[str]:
        return [
            self.command_name,
            "-p",
            file_path,
            "-o",
            output_dir,
            "--backend",
            self.backend,
            "-m",
            self.method,
        ]

    def _run_command(self, cmd: List[str]) -> subprocess.CompletedProcess:
        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(cmd, **popen_kwargs)
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            self._terminate_process_group(process)
            try:
                extra_stdout, extra_stderr = process.communicate(timeout=5)
                stdout = (stdout or "") + (extra_stdout or "")
                stderr = (stderr or "") + (extra_stderr or "")
            except Exception:
                pass
            raise MinerUTimeout(self.timeout_seconds, stdout_tail=_tail(stdout), stderr_tail=_tail(stderr))

        return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)

    def _terminate_process_group(self, process: subprocess.Popen) -> None:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def is_available(self) -> bool:
        if shutil.which(self.command_name):
            return True
        return importlib.util.find_spec("mineru") is not None or importlib.util.find_spec("magic_pdf") is not None

    def _find_output_artifact(self, output_dir: Path) -> Optional[Path]:
        markdown_files = sorted(output_dir.rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True)
        if markdown_files:
            return markdown_files[0]
        json_files = sorted(output_dir.rglob("*.json"), key=lambda p: p.stat().st_size, reverse=True)
        return json_files[0] if json_files else None

    def _parse_markdown_artifact(self, file_path: str, artifact: Path) -> ParsedDocument:
        text = _normalize_markdown_text(artifact.read_text(encoding="utf-8", errors="replace"))
        total_pages = _safe_pdf_page_count(file_path)
        sections = _sections_from_markdown_pages(text)
        if not sections and text.strip():
            sections = [ParsedSection(text=text, location="mineru:markdown")]
        status, quality = _status_from_sections(sections, total_pages)
        hints = _pdf_quality_hints(
            total_pages=total_pages,
            total_chars=sum(len(section.text or "") for section in sections),
            total_words=sum(len((section.text or "").split()) for section in sections),
            empty_pages=max(0, total_pages - len([s for s in sections if (s.text or "").strip()])),
            image_count=_count_markdown_placeholders(text, "image"),
            table_count=_estimate_table_like_blocks(text),
            quality_score=quality,
            fallback_used=False,
            fallback_reason="",
        )
        return ParsedDocument(
            file_path=file_path,
            parser_type="pdf:mineru",
            parser_version="mineru-local",
            extraction_status=status,
            extraction_quality=quality,
            sections=sections,
            metadata_hints=hints,
        )

    def _parse_json_artifact(self, file_path: str, artifact: Path) -> ParsedDocument:
        data = json.loads(artifact.read_text(encoding="utf-8", errors="replace"))
        sections, image_count, table_count = _sections_from_mineru_json(data)
        total_pages = _safe_pdf_page_count(file_path)
        status, quality = _status_from_sections(sections, total_pages)
        hints = _pdf_quality_hints(
            total_pages=total_pages,
            total_chars=sum(len(section.text or "") for section in sections),
            total_words=sum(len((section.text or "").split()) for section in sections),
            empty_pages=max(0, total_pages - len([s for s in sections if (s.text or "").strip()])),
            image_count=image_count,
            table_count=table_count,
            quality_score=quality,
            fallback_used=False,
            fallback_reason="",
        )
        return ParsedDocument(
            file_path=file_path,
            parser_type="pdf:mineru",
            parser_version="mineru-local",
            extraction_status=status,
            extraction_quality=quality,
            sections=sections,
            metadata_hints=hints,
        )


class PyMuPDFDocumentParser(PdfDocumentParser):
    pass


class MinerUFullDocumentParser(MinerUPdfParser):
    pass


class MinerUSelectivePageParser(DocumentParser):
    supported_extensions = {".pdf"}

    def __init__(self, mineru_parser: Optional[DocumentParser] = None):
        self.mineru_parser = mineru_parser or MinerUFullDocumentParser()

    def parse_selected_pages(
        self,
        file_path: str,
        selected_pages: List[int],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ParsedDocument:
        selected_pages = [int(page) for page in selected_pages if int(page) > 0]
        print(
            "[MinerUSelectivePageParser] "
            f"file={file_path} selected_pages={selected_pages} "
            f"ranges={_pages_to_ranges(selected_pages)} "
            f"max_pages={getattr(Config, 'MINERU_SELECTIVE_MAX_PAGES_PER_DOC', 20)}"
        )
        sections: List[ParsedSection] = []
        warnings: List[str] = []
        failed_pages: List[int] = []

        if not selected_pages:
            return ParsedDocument(
                file_path=file_path,
                parser_type="pdf:mineru_selective",
                parser_version="mineru-selective-local",
                extraction_status="EMPTY_DOCUMENT",
                extraction_quality=0.0,
                warnings=["No selective pages were selected."],
                metadata_hints={"selected_pages": [], "selective_failed_pages": []},
            )

        with tempfile.TemporaryDirectory(prefix="mineru_selective_") as tmpdir:
            for page_number in selected_pages:
                page_pdf = Path(tmpdir) / f"page_{page_number}.pdf"
                try:
                    _write_single_page_pdf(file_path, page_number, page_pdf)
                    parsed_page = _call_parser(self.mineru_parser, str(page_pdf), metadata)
                    page_sections = parsed_page.sections or []
                    for section in page_sections:
                        section.page = page_number
                        section.location = f"page:{page_number}"
                    sections.extend(page_sections)
                    print(
                        "[MinerUSelectivePageParser] "
                        f"page={page_number} status=ok chars={sum(len(s.text or '') for s in page_sections)}"
                    )
                except Exception as exc:
                    failed_pages.append(page_number)
                    warning = f"page={page_number} failed: {_log_reason(exc)}"
                    warnings.append(warning)
                    print(
                        "[MinerUSelectivePageParser] "
                        f"page={page_number} status=failed fallback=original_pymupdf reason={_log_reason(exc)}"
                    )

        total_chars = sum(len(section.text or "") for section in sections)
        status = "CHUNKED" if sections else "EMPTY_DOCUMENT"
        quality = 1.0 if sections else 0.0
        print(
            "[MinerUSelectivePageParser] "
            f"status=completed parsed_pages={len(set(s.page for s in sections if s.page))} "
            f"failed_pages={failed_pages}"
        )
        return ParsedDocument(
            file_path=file_path,
            parser_type="pdf:mineru_selective",
            parser_version="mineru-selective-local",
            extraction_status=status,
            extraction_quality=quality,
            sections=sections,
            warnings=warnings,
            metadata_hints={
                "selected_pages": selected_pages,
                "selective_failed_pages": failed_pages,
                "quality": {
                    "total_chars": total_chars,
                    "total_words": sum(len((section.text or "").split()) for section in sections),
                    "quality_score": quality,
                    "selected_pages": selected_pages,
                    "selective_failed_pages": failed_pages,
                },
            },
        )


class ParseOutputQualityEvaluator:
    def evaluate(self, parsed: ParsedDocument, probe: Optional[PdfProbeResult] = None) -> Dict[str, Any]:
        chars = parsed.extracted_char_count
        total_pages = probe.total_pages if probe else int((parsed.metadata_hints or {}).get("total_pages") or 0)
        empty_ratio = 0.0
        if probe and probe.total_pages:
            empty_ratio = probe.empty_pages_count / max(1, probe.total_pages)
        duplicate_ratio = _duplicate_text_ratio(parsed.text)
        text_coverage = chars / max(1, probe.total_chars) if probe and probe.total_chars else 1.0 if chars else 0.0
        quality_score = max(0.0, min(1.0, parsed.extraction_quality or 0.0))
        if parsed.extraction_status in {"FAILED", "EMPTY_DOCUMENT"}:
            quality_score = 0.0
        elif duplicate_ratio > 0.55:
            quality_score *= 0.75
        return {
            "chars": chars,
            "words": parsed.extracted_word_count,
            "total_pages": total_pages,
            "text_coverage": round(text_coverage, 4),
            "empty_page_ratio": round(empty_ratio, 4),
            "duplicate_text_ratio": round(duplicate_ratio, 4),
            "table_structure_score": 0.5,
            "caption_preservation_score": 0.5,
            "page_mapping_ok": True,
            "quality_score": round(quality_score, 4),
            "warnings": parsed.warnings,
        }

    def is_usable(
        self,
        parsed: ParsedDocument,
        probe: Optional[PdfProbeResult] = None,
        baseline: Optional[ParsedDocument] = None,
    ) -> bool:
        metrics = self.evaluate(parsed, probe)
        if parsed.extraction_status in {"FAILED", "EMPTY_DOCUMENT"}:
            return False
        if parsed.extracted_char_count <= 0:
            return False
        if baseline and baseline.extracted_char_count > 1000 and parsed.extracted_char_count < baseline.extracted_char_count * 0.35:
            return False
        return metrics["quality_score"] >= 0.2


class ParsedDocumentMerger:
    def merge(
        self,
        plan: ParsePlan,
        base_document: ParsedDocument,
        advanced_document: Optional[ParsedDocument] = None,
        evaluator: Optional[ParseOutputQualityEvaluator] = None,
        probe: Optional[PdfProbeResult] = None,
    ) -> ParsedDocument:
        evaluator = evaluator or ParseOutputQualityEvaluator()
        if plan.plan_type == "pymupdf_only" or not advanced_document:
            _apply_plan_metadata(base_document, plan, probe)
            return base_document

        if plan.plan_type == "mineru_full":
            if evaluator.is_usable(advanced_document, probe, baseline=base_document):
                _apply_plan_metadata(advanced_document, plan, probe)
                return advanced_document
            _mark_fallback(base_document, used=True, reason="mineru_output_not_usable")
            _apply_plan_metadata(base_document, plan, probe)
            return base_document

        if plan.plan_type == "pymupdf_plus_mineru_selective":
            merged_sections = self._merge_selective_sections(base_document, advanced_document, plan)
            quality = min(1.0, max(base_document.extraction_quality, advanced_document.extraction_quality))
            merged = ParsedDocument(
                file_path=base_document.file_path,
                parser_type="pdf:pymupdf+mineru_selective",
                parser_version=f"{base_document.parser_version}+{advanced_document.parser_version}",
                extraction_status="CHUNKED" if merged_sections else base_document.extraction_status,
                extraction_quality=quality,
                sections=merged_sections or base_document.sections,
                warnings=list(base_document.warnings) + list(advanced_document.warnings),
                metadata_hints=dict(base_document.metadata_hints or {}),
            )
            _apply_plan_metadata(merged, plan, probe)
            quality_hints = dict((merged.metadata_hints or {}).get("quality") or {})
            quality_hints["selective_failed_pages"] = (advanced_document.metadata_hints or {}).get("selective_failed_pages", [])
            merged.metadata_hints["selective_failed_pages"] = quality_hints["selective_failed_pages"]
            merged.metadata_hints["quality"] = quality_hints
            return merged

        _apply_plan_metadata(base_document, plan, probe)
        return base_document

    def _merge_selective_sections(
        self,
        base_document: ParsedDocument,
        selective_document: ParsedDocument,
        plan: ParsePlan,
    ) -> List[ParsedSection]:
        advanced_by_page: Dict[int, List[ParsedSection]] = {}
        for section in selective_document.sections:
            if section.page:
                advanced_by_page.setdefault(section.page, []).append(section)

        merged: List[ParsedSection] = []
        seen_pages = set()
        low_text_threshold = int(plan.config_snapshot.get("mineru_selective_low_text_chars", 300))
        for section in base_document.sections:
            page = section.page
            if not page or page not in advanced_by_page:
                merged.append(section)
                continue
            seen_pages.add(page)
            advanced_text = "\n\n".join(_normalize_markdown_text(s.text) for s in advanced_by_page.get(page, []) if s.text)
            if not advanced_text:
                merged.append(section)
                continue
            base_text = _normalize_markdown_text(section.text)
            if _dedupe_key(advanced_text) and _dedupe_key(advanced_text) in _dedupe_key(base_text):
                merged.append(section)
                continue
            if len(base_text) < low_text_threshold:
                merged.append(
                    ParsedSection(
                        text=f"[Page {page}]\n{advanced_text}",
                        page=page,
                        location=f"page:{page}",
                    )
                )
            else:
                merged.append(
                    ParsedSection(
                        text=f"{base_text}\n\n[Advanced MinerU Parse page={page}]\n{advanced_text}",
                        page=page,
                        location=f"page:{page}",
                    )
                )

        for page, sections in advanced_by_page.items():
            if page in seen_pages:
                continue
            advanced_text = "\n\n".join(_normalize_markdown_text(s.text) for s in sections if s.text)
            if advanced_text:
                merged.append(ParsedSection(text=f"[Advanced MinerU Parse page={page}]\n{advanced_text}", page=page, location=f"page:{page}"))
        return merged


class PdfParsePlanner:
    def __init__(self):
        self.selective_enabled = _to_bool(getattr(Config, "MINERU_SELECTIVE_BOOK_PAGES_ENABLED", True))
        self.max_pages = int(getattr(Config, "MINERU_SELECTIVE_MAX_PAGES_PER_DOC", 20) or 20)
        self.max_ranges = int(getattr(Config, "MINERU_SELECTIVE_MAX_RANGES_PER_DOC", 10) or 10)
        self.low_text_chars = int(getattr(Config, "MINERU_SELECTIVE_LOW_TEXT_CHARS", 300) or 300)
        self.table_threshold = float(getattr(Config, "MINERU_SELECTIVE_TABLE_LIKE_THRESHOLD", 0.25) or 0.25)
        self.image_area_ratio = float(getattr(Config, "MINERU_SELECTIVE_IMAGE_AREA_RATIO", 0.20) or 0.20)
        self.full_max_pages = int(getattr(Config, "MINERU_FULL_MAX_PAGES_SOFT_LIMIT", 80) or 80)
        self.full_complex_ratio = float(getattr(Config, "MINERU_FULL_COMPLEX_PAGE_RATIO_THRESHOLD", 0.35) or 0.35)

    def build_plan(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]],
        probe: PdfProbeResult,
        mode: str,
        mineru_parse_books: bool = False,
    ) -> ParsePlan:
        mode = (mode or "pymupdf").strip().lower()
        knowledge_type, inferred = self._knowledge_type(file_path, metadata, probe)
        warnings: List[str] = []
        if inferred:
            warning = f"knowledge_type_inferred_from_path file={file_path} inferred={knowledge_type}"
            warnings.append(warning)
            print(f"[PdfParsePlanner] warning={warning}")
        config = self._config_snapshot(mode, mineru_parse_books)
        selected_pages = self._selected_pages(probe)
        selected_ranges = _pages_to_ranges(selected_pages)[: self.max_ranges]

        if mode == "pymupdf":
            plan = ParsePlan("pymupdf_only", "pdf:pymupdf", reason="mode_pymupdf", knowledge_type=knowledge_type)
        elif knowledge_type == "report":
            plan = self._report_plan(probe, config, selected_pages, selected_ranges)
            plan.knowledge_type = knowledge_type
        elif knowledge_type == "book":
            plan = self._book_plan(metadata, probe, config, selected_pages, selected_ranges, mineru_parse_books)
            plan.knowledge_type = knowledge_type
        else:
            if probe.needs_ocr:
                plan = ParsePlan("mineru_full", "pdf:pymupdf", "pdf:mineru", reason="unknown_needs_ocr_mineru", knowledge_type=knowledge_type)
            else:
                plan = ParsePlan("pymupdf_only", "pdf:pymupdf", reason="unknown_default_pymupdf", knowledge_type=knowledge_type)

        plan.config_snapshot = config
        plan.probe_summary = _probe_summary(probe)
        plan.probe_summary["selected_page_reasons"] = {
            page.human_page_number: page.reasons
            for page in probe.page_metrics
            if page.human_page_number in plan.selected_pages
        }
        plan.warnings.extend(warnings)
        print(
            "[PdfParsePlanner] "
            f"file={file_path} knowledge_type={plan.knowledge_type} plan={plan.plan_type} "
            f"reason={plan.reason} selected_pages={plan.selected_pages[:10]}"
        )
        return plan

    def _report_plan(
        self,
        probe: PdfProbeResult,
        config: Dict[str, Any],
        selected_pages: List[int],
        selected_ranges: List[tuple[int, int]],
    ) -> ParsePlan:
        if (
            probe.total_pages > self.full_max_pages
            and selected_pages
        ):
            return ParsePlan(
                "pymupdf_plus_mineru_selective",
                "pdf:pymupdf",
                "pdf:mineru_selective",
                selected_pages=selected_pages,
                selected_ranges=selected_ranges,
                reason="large_report_selective_mineru",
                confidence=0.82,
            )
        if probe.total_pages > self.full_max_pages:
            if not selected_pages and probe.avg_chars_per_page >= 900 and probe.layout_complexity == "low":
                return ParsePlan("pymupdf_only", "pdf:pymupdf", reason="simple_text_report_pymupdf", confidence=0.75)
            return ParsePlan(
                "pymupdf_only",
                "pdf:pymupdf",
                reason="large_report_avoid_full_mineru",
                confidence=0.68,
                warnings=[
                    f"Report has {probe.total_pages} pages, above MinerU full soft limit {self.full_max_pages}; "
                    "using PyMuPDF to avoid local OOM."
                ],
            )
        return ParsePlan("mineru_full", "pdf:pymupdf", "pdf:mineru", reason="report_full_mineru", confidence=0.9)

    def _book_plan(
        self,
        metadata: Optional[Dict[str, Any]],
        probe: PdfProbeResult,
        config: Dict[str, Any],
        selected_pages: List[int],
        selected_ranges: List[tuple[int, int]],
        mineru_parse_books: bool,
    ) -> ParsePlan:
        if _manifest_prefers_mineru(metadata):
            return ParsePlan("mineru_full", "pdf:pymupdf", "pdf:mineru", reason="manifest_override", confidence=0.9)
        if mineru_parse_books:
            return ParsePlan("mineru_full", "pdf:pymupdf", "pdf:mineru", reason="mineru_books_enabled", confidence=0.85)
        if probe.needs_ocr and probe.scanned_likelihood == "high":
            return ParsePlan("mineru_full", "pdf:pymupdf", "pdf:mineru", reason="book_scan_heavy_mineru", confidence=0.86)
        if self._clean_text_book_probe(probe):
            return ParsePlan("pymupdf_only", "pdf:pymupdf", reason="book_text_based_pymupdf", confidence=0.94)
        if self.selective_enabled and selected_pages:
            return ParsePlan(
                "pymupdf_plus_mineru_selective",
                "pdf:pymupdf",
                "pdf:mineru_selective",
                selected_pages=selected_pages,
                selected_ranges=selected_ranges,
                reason="book_base_pymupdf_selective_mineru",
                confidence=0.82,
            )
        return ParsePlan("pymupdf_only", "pdf:pymupdf", reason="book_text_based_pymupdf", confidence=0.9)

    def _selected_pages(self, probe: PdfProbeResult) -> List[int]:
        selected: List[int] = []
        for page in probe.page_metrics:
            if len(selected) >= self.max_pages:
                break
            if page.complexity_score < 0.45:
                continue
            if page.low_text_density and page.image_count > 0:
                selected.append(page.human_page_number)
            elif page.image_area_ratio >= self.image_area_ratio:
                selected.append(page.human_page_number)
            elif page.table_like_ratio >= self.table_threshold:
                selected.append(page.human_page_number)
            elif page.likely_chart_or_figure_caption or page.likely_table_caption:
                selected.append(page.human_page_number)
            elif page.likely_scan_or_ocr_page or page.multi_column_likelihood:
                selected.append(page.human_page_number)
        return selected[: self.max_pages]

    def _clean_text_book_probe(self, probe: PdfProbeResult) -> bool:
        return (
            not probe.needs_ocr
            and probe.scanned_likelihood == "low"
            and probe.layout_complexity == "low"
            and probe.image_count == 0
            and probe.empty_pages_count == 0
            and probe.avg_chars_per_page >= 600
            and probe.table_like_ratio < min(0.05, self.table_threshold)
            and not probe.selected_candidate_pages
        )

    def _knowledge_type(self, file_path: str, metadata: Optional[Dict[str, Any]], probe: PdfProbeResult) -> tuple[str, bool]:
        value = _metadata_value(metadata, "knowledge_type").lower()
        if value:
            return value, False
        if probe.inferred_knowledge_type:
            return probe.inferred_knowledge_type, True
        inferred = _infer_knowledge_type(file_path, metadata)
        return inferred or "unknown", bool(inferred)

    def _config_snapshot(self, mode: str, mineru_parse_books: bool) -> Dict[str, Any]:
        return {
            "pdf_parser_mode": mode,
            "mineru_command": getattr(Config, "MINERU_COMMAND", ""),
            "mineru_backend": getattr(Config, "MINERU_BACKEND", "pipeline"),
            "mineru_method": getattr(Config, "MINERU_METHOD", "auto"),
            "mineru_timeout_seconds": int(getattr(Config, "MINERU_TIMEOUT_SECONDS", 1800) or 1800),
            "mineru_parse_books": _to_bool(mineru_parse_books),
            "mineru_selective_book_pages_enabled": self.selective_enabled,
            "mineru_selective_max_pages_per_doc": self.max_pages,
            "mineru_selective_max_ranges_per_doc": self.max_ranges,
            "mineru_selective_low_text_chars": self.low_text_chars,
            "mineru_selective_table_like_threshold": self.table_threshold,
            "mineru_selective_image_area_ratio": self.image_area_ratio,
            "mineru_full_max_pages_soft_limit": self.full_max_pages,
            "mineru_full_complex_page_ratio_threshold": self.full_complex_ratio,
            "parser_output_schema_version": PARSER_OUTPUT_SCHEMA_VERSION,
        }


class PdfParserRouter(DocumentParser):
    supported_extensions = {".pdf"}

    def __init__(
        self,
        mode: Optional[str] = None,
        mineru_parser: Optional[DocumentParser] = None,
        fallback_parser: Optional[DocumentParser] = None,
        mineru_parse_books: Optional[bool] = None,
        probe_service: Optional[PyMuPDFProbeService] = None,
        planner: Optional[PdfParsePlanner] = None,
        selective_parser: Optional[MinerUSelectivePageParser] = None,
        quality_evaluator: Optional[ParseOutputQualityEvaluator] = None,
        merger: Optional[ParsedDocumentMerger] = None,
    ):
        self.mode = (mode or getattr(Config, "PDF_PARSER_MODE", "pymupdf") or "pymupdf").strip().lower()
        self.mineru_parser = mineru_parser or MinerUFullDocumentParser()
        self.fallback_parser = fallback_parser or PyMuPDFDocumentParser()
        self.mineru_parse_books = (
            _to_bool(mineru_parse_books)
            if mineru_parse_books is not None
            else _to_bool(getattr(Config, "MINERU_PARSE_BOOKS", False))
        )
        self.probe_service = probe_service or PyMuPDFProbeService()
        self.planner = planner or PdfParsePlanner()
        self.selective_parser = selective_parser or MinerUSelectivePageParser(self.mineru_parser)
        self.quality_evaluator = quality_evaluator or ParseOutputQualityEvaluator()
        self.merger = merger or ParsedDocumentMerger()

    def parse(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> ParsedDocument:
        probe = self.probe_service.probe(file_path, metadata)
        mode = self.mode if self.mode in {"pymupdf", "mineru_first", "adaptive"} else "pymupdf"
        if mode != self.mode:
            print(f"[PdfParsePlanner] warning=invalid_mode file={file_path} mode={self.mode} fallback=pymupdf")
        plan = self.planner.build_plan(file_path, metadata, probe, mode, self.mineru_parse_books)

        if plan.plan_type == "pymupdf_only":
            base = self._parse_pymupdf(file_path, metadata, plan, fallback_used=False, fallback_reason="")
            return self.merger.merge(plan, base, evaluator=self.quality_evaluator, probe=probe)

        if plan.plan_type == "mineru_full":
            base: Optional[ParsedDocument] = None
            try:
                advanced = self._parse_mineru_full(file_path, metadata, plan)
                if advanced.extraction_status in {"FAILED", "EMPTY_DOCUMENT"}:
                    raise MinerUFailed(f"MinerU returned status={advanced.extraction_status}")
                if advanced.extraction_status == "NEEDS_OCR":
                    if not advanced.text.strip():
                        raise MinerUFailed("MinerU returned NEEDS_OCR with no usable text")
                    advanced.warnings.append("MinerU returned NEEDS_OCR but usable text was preserved; indexing with caution.")
                if self.quality_evaluator.is_usable(advanced, probe):
                    base = self._parse_pymupdf(file_path, metadata, plan, fallback_used=False, fallback_reason="")
                    return self.merger.merge(plan, base, advanced, self.quality_evaluator, probe)
                raise MinerUFailed("MinerU output was not usable.")
            except MinerUUnavailable as exc:
                print(f"[MinerUParser] status=unavailable fallback=pdf:pymupdf reason={_log_reason(exc)}")
                return self._fallback(file_path, metadata, plan, f"mineru_unavailable:{exc}")
            except MinerUTimeout as exc:
                print(
                    "[MinerUParser] status=timeout fallback=pdf:pymupdf "
                    f"timeout_seconds={exc.timeout_seconds}"
                )
                return self._fallback(file_path, metadata, plan, f"mineru_timeout:{exc.timeout_seconds}s")
            except MinerUFailed as exc:
                print(
                    "[MinerUParser] status=failed fallback=pdf:pymupdf "
                    f"returncode={exc.returncode} stderr_tail={_log_reason(exc.stderr_tail or exc)}"
                )
                return self._fallback(file_path, metadata, plan, f"mineru_failed:{exc}")
            except Exception as exc:
                print(f"[MinerUParser] status=failed fallback=pdf:pymupdf reason={_log_reason(exc)}")
                return self._fallback(file_path, metadata, plan, f"mineru_failed:{exc}")

        if plan.plan_type == "pymupdf_plus_mineru_selective":
            base = self._parse_pymupdf(file_path, metadata, plan, fallback_used=False, fallback_reason="")
            advanced = self.selective_parser.parse_selected_pages(file_path, plan.selected_pages, metadata)
            _mark_pdf_parser_config(advanced, self.mode, self.mineru_parse_books, self.mineru_parser, plan)
            return self.merger.merge(plan, base, advanced, self.quality_evaluator, probe)

        base = self._parse_pymupdf(file_path, metadata, plan, fallback_used=True, fallback_reason=f"unknown_plan:{plan.plan_type}")
        return self.merger.merge(plan, base, evaluator=self.quality_evaluator, probe=probe)

    def _parse_pymupdf(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]],
        plan: ParsePlan,
        fallback_used: bool,
        fallback_reason: str,
    ) -> ParsedDocument:
        print(f"[PdfParserRouter] file={file_path} mode={self.mode} selected=pdf:pymupdf reason={plan.reason}")
        parsed = _call_parser(self.fallback_parser, file_path, metadata)
        _mark_fallback(parsed, used=fallback_used, reason=fallback_reason)
        _mark_pdf_parser_config(parsed, self.mode, self.mineru_parse_books, self.mineru_parser, plan)
        return parsed

    def _parse_mineru_full(self, file_path: str, metadata: Optional[Dict[str, Any]], plan: ParsePlan) -> ParsedDocument:
        print(f"[PdfParserRouter] file={file_path} mode={self.mode} selected=pdf:mineru reason={plan.reason}")
        parsed = _call_parser(self.mineru_parser, file_path, metadata)
        _mark_fallback(parsed, used=False, reason="")
        _mark_pdf_parser_config(parsed, self.mode, self.mineru_parse_books, self.mineru_parser, plan)
        return parsed

    def _fallback(self, file_path: str, metadata: Optional[Dict[str, Any]], plan: ParsePlan, reason: str) -> ParsedDocument:
        print(f"[PdfParserFallback] selected=pdf:pymupdf fallback_reason={_log_reason(reason)}")
        return self._parse_pymupdf(file_path, metadata, plan, fallback_used=True, fallback_reason=reason)


class EpubDocumentParser(DocumentParser):
    supported_extensions = {".epub"}

    def parse(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> ParsedDocument:
        parser_version = "stdlib-zip-xml-html"
        warnings: List[str] = []
        try:
            with zipfile.ZipFile(file_path) as archive:
                opf_path = self._find_opf_path(archive)
                if not opf_path:
                    return self._failed(file_path, parser_version, "EPUB container.opf not found.")

                opf_root = ET.fromstring(archive.read(opf_path))
                base_dir = str(Path(opf_path).parent).replace("\\", "/")
                if base_dir == ".":
                    base_dir = ""

                manifest = self._read_manifest(opf_root)
                spine_ids = self._read_spine(opf_root)
                title_hint = self._find_metadata_text(opf_root, "title")
                author_hint = self._find_metadata_text(opf_root, "creator")

                sections: List[ParsedSection] = []
                for spine_index, item_id in enumerate(spine_ids, start=1):
                    href = manifest.get(item_id)
                    if not href:
                        continue
                    item_path = f"{base_dir}/{href}".strip("/")
                    try:
                        raw_html = archive.read(item_path).decode("utf-8", errors="replace")
                    except KeyError:
                        warnings.append(f"Missing EPUB item: {item_path}")
                        continue

                    text = _html_to_text(raw_html)
                    if not text.strip():
                        continue
                    chapter = _first_non_empty_line(text) or f"Chapter {spine_index}"
                    sections.append(
                        ParsedSection(
                            text=text,
                            chapter=chapter,
                            section=chapter,
                            location=f"spine:{spine_index}",
                            spine_index=spine_index,
                            href=item_path,
                            paragraph_index=1,
                        )
                    )
        except Exception as exc:
            return self._failed(file_path, parser_version, str(exc))

        if not sections:
            status = "EMPTY_DOCUMENT"
            quality = 0.0
        else:
            status = "CHUNKED"
            quality = 1.0

        return ParsedDocument(
            file_path=file_path,
            parser_type="epub:zip",
            parser_version=parser_version,
            extraction_status=status,
            extraction_quality=quality,
            sections=sections,
            warnings=warnings,
            metadata_hints={
                "title": title_hint,
                "author": author_hint,
                "section_count": len(sections),
            },
        )

    def _failed(self, file_path: str, parser_version: str, message: str) -> ParsedDocument:
        return ParsedDocument(
            file_path=file_path,
            parser_type="epub:zip",
            parser_version=parser_version,
            extraction_status="FAILED",
            extraction_quality=0.0,
            warnings=[message],
        )

    def _find_opf_path(self, archive: zipfile.ZipFile) -> Optional[str]:
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            for elem in container.iter():
                if _strip_namespace(elem.tag) == "rootfile":
                    path = elem.attrib.get("full-path")
                    if path:
                        return path
        except Exception:
            pass

        for name in archive.namelist():
            if name.lower().endswith(".opf"):
                return name
        return None

    def _read_manifest(self, opf_root: ET.Element) -> Dict[str, str]:
        manifest: Dict[str, str] = {}
        for elem in opf_root.iter():
            if _strip_namespace(elem.tag) == "item":
                item_id = elem.attrib.get("id")
                href = elem.attrib.get("href")
                media_type = elem.attrib.get("media-type", "")
                if item_id and href and ("html" in media_type or href.lower().endswith((".xhtml", ".html", ".htm"))):
                    manifest[item_id] = href
        return manifest

    def _read_spine(self, opf_root: ET.Element) -> List[str]:
        ids: List[str] = []
        for elem in opf_root.iter():
            if _strip_namespace(elem.tag) == "itemref":
                item_id = elem.attrib.get("idref")
                if item_id:
                    ids.append(item_id)
        return ids

    def _find_metadata_text(self, opf_root: ET.Element, local_name: str) -> str:
        for elem in opf_root.iter():
            if _strip_namespace(elem.tag) == local_name and elem.text:
                return elem.text.strip()
        return ""


class DocumentParserRegistry:
    def __init__(self, parsers: Optional[List[DocumentParser]] = None):
        self.parsers = parsers or [PdfParserRouter(), EpubDocumentParser()]

    @property
    def supported_extensions(self) -> set[str]:
        extensions = set()
        for parser in self.parsers:
            extensions.update(parser.supported_extensions)
        return extensions

    def get_parser(self, file_path: str) -> DocumentParser:
        extension = Path(file_path).suffix.lower()
        for parser in self.parsers:
            if extension in parser.supported_extensions:
                return parser
        raise ValueError(f"Unsupported document extension: {extension}")

    def parse(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> ParsedDocument:
        return _call_parser(self.get_parser(file_path), file_path, metadata)


def _call_parser(parser: DocumentParser, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> ParsedDocument:
    parameters = inspect.signature(parser.parse).parameters
    if len(parameters) >= 2:
        return parser.parse(file_path, metadata)
    return parser.parse(file_path)


def _metadata_value(metadata: Optional[Dict[str, Any]], key: str) -> str:
    if not isinstance(metadata, dict):
        return ""
    for section_name in ("routing_metadata", "document_metadata"):
        section = metadata.get(section_name) or {}
        if isinstance(section, dict) and section.get(key) not in (None, ""):
            return str(section.get(key) or "").strip()
    value = metadata.get(key)
    return str(value or "").strip()


def _manifest_prefers_mineru(metadata: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(metadata, dict):
        return False
    parser = metadata.get("parser") or {}
    if not isinstance(parser, dict):
        return False
    return str(parser.get("preferred") or parser.get("preferred_parser") or "").strip().lower() == "mineru"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _infer_knowledge_type(file_path: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    value = _metadata_value(metadata, "knowledge_type").lower()
    if value:
        return value
    parts = [part.lower() for part in Path(file_path).parts]
    if "knowledge_repository" in parts:
        idx = parts.index("knowledge_repository")
        if len(parts) > idx + 1 and parts[idx + 1] in {"book", "report"}:
            return parts[idx + 1]
    return ""


def _page_image_area_ratio(page: Any) -> float:
    try:
        page_area = max(1.0, float(page.rect.width * page.rect.height))
        total_area = 0.0
        for image in page.get_images(full=True):
            xref = image[0]
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            for rect in rects:
                area = max(0.0, float(rect.width * rect.height))
                if area / page_area >= 0.005:
                    total_area += area
        return min(1.0, total_area / page_area)
    except Exception:
        return 0.0


def _table_like_ratio(text: str) -> float:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return 0.0
    table_like = 0
    for line in lines:
        separators = line.count("|") + line.count("\t")
        digit_ratio = sum(ch.isdigit() for ch in line) / max(1, len(line))
        percent_count = line.count("%")
        if separators >= 2 or percent_count >= 2 or digit_ratio > 0.35:
            table_like += 1
    return table_like / max(1, len(lines))


def _has_figure_caption(text: str) -> bool:
    return bool(re.search(r"(?im)\b(fig(?:ure)?\.?|chart|exhibit|panel)\s*[:.\-\d]", text or ""))


def _has_table_caption(text: str) -> bool:
    return bool(re.search(r"(?im)\b(table|source:|note:|appendix)\s*[:.\-\d]", text or ""))


def _multi_column_likelihood(text: str) -> bool:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if len(lines) < 12:
        return False
    short_lines = sum(1 for line in lines if 20 <= len(line.strip()) <= 65)
    return short_lines / max(1, len(lines)) > 0.65


def _page_complexity_score(
    low_text_density: bool,
    image_area_ratio: float,
    table_like_ratio: float,
    figure_caption: bool,
    table_caption: bool,
    scan_page: bool,
    multi_column: bool,
) -> float:
    score = 0.0
    if low_text_density:
        score += 0.18
    score += min(0.28, image_area_ratio)
    score += min(0.30, table_like_ratio)
    if figure_caption:
        score += 0.14
    if table_caption:
        score += 0.14
    if scan_page:
        score += 0.22
    if multi_column:
        score += 0.10
    return min(1.0, score)


def _top_probe_reasons(pages: List[PageProbeResult]) -> List[str]:
    counts: Dict[str, int] = {}
    for page in pages:
        for reason in page.reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return [reason for reason, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]]


def _pages_to_ranges(pages: List[int]) -> List[tuple[int, int]]:
    ordered = sorted({int(page) for page in pages if int(page) > 0})
    if not ordered:
        return []
    ranges: List[tuple[int, int]] = []
    start = prev = ordered[0]
    for page in ordered[1:]:
        if page == prev + 1:
            prev = page
            continue
        ranges.append((start, prev))
        start = prev = page
    ranges.append((start, prev))
    return ranges


def _write_single_page_pdf(file_path: str, page_number: int, output_path: Path) -> None:
    source = fitz.open(file_path)
    try:
        if page_number < 1 or page_number > len(source):
            raise ValueError(f"page out of range: {page_number}")
        target = fitz.open()
        try:
            target.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1)
            target.save(str(output_path))
        finally:
            target.close()
    finally:
        source.close()


def _duplicate_text_ratio(text: str) -> float:
    paragraphs = [_dedupe_key(part) for part in re.split(r"\n\s*\n", text or "") if _dedupe_key(part)]
    if not paragraphs:
        return 0.0
    return 1.0 - (len(set(paragraphs)) / max(1, len(paragraphs)))


def _dedupe_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())[:2000]


def _probe_summary(probe: Optional[PdfProbeResult]) -> Dict[str, Any]:
    if not probe:
        return {}
    return {
        "total_pages": probe.total_pages,
        "total_chars": probe.total_chars,
        "total_words": probe.total_words,
        "avg_chars_per_page": probe.avg_chars_per_page,
        "empty_pages_count": probe.empty_pages_count,
        "image_count": probe.image_count,
        "table_count": probe.table_count,
        "table_like_ratio": probe.table_like_ratio,
        "scanned_likelihood": probe.scanned_likelihood,
        "needs_ocr": probe.needs_ocr,
        "layout_complexity": probe.layout_complexity,
        "complex_page_ratio": round(probe.complex_page_ratio, 4),
    }


def _selected_page_reasons(plan: ParsePlan) -> Dict[int, List[str]]:
    raw = (plan.probe_summary or {}).get("selected_page_reasons", {}) if isinstance(plan.probe_summary, dict) else {}
    return {int(page): list(reasons or []) for page, reasons in raw.items()}


def _apply_plan_metadata(parsed: ParsedDocument, plan: ParsePlan, probe: Optional[PdfProbeResult]) -> None:
    hints = dict(parsed.metadata_hints or {})
    quality = dict(hints.get("quality") or {})
    fields = {
        "parse_plan_type": plan.plan_type,
        "parse_plan_reason": plan.reason,
        "base_parser": plan.base_parser,
        "advanced_parser": plan.advanced_parser,
        "selective_enabled": plan.plan_type == "pymupdf_plus_mineru_selective",
        "selective_pages": plan.selected_pages,
        "selective_page_count": len(plan.selected_pages),
        "selected_page_reasons": _selected_page_reasons(plan),
        "parser_output_schema_version": PARSER_OUTPUT_SCHEMA_VERSION,
    }
    if probe:
        fields.update(_probe_summary(probe))
    fields.update(plan.config_snapshot or {})
    hints.update(fields)
    quality.update(fields)
    hints["quality"] = quality
    parsed.metadata_hints = hints


def _pdf_quality_hints(
    total_pages: int,
    total_chars: int,
    total_words: int,
    empty_pages: int,
    image_count: int,
    table_count: int,
    quality_score: float,
    fallback_used: bool,
    fallback_reason: str,
) -> Dict[str, Any]:
    avg_chars = total_chars / total_pages if total_pages else 0.0
    scanned_likelihood = total_pages > 0 and empty_pages / max(1, total_pages) >= 0.8 and image_count > 0
    needs_ocr = quality_score < 0.2 or scanned_likelihood
    quality = {
        "total_pages": total_pages,
        "total_chars": total_chars,
        "total_words": total_words,
        "avg_chars_per_page": round(avg_chars, 2),
        "empty_pages_count": empty_pages,
        "empty_pages": empty_pages,
        "image_count": image_count,
        "table_count": table_count,
        "scanned_likelihood": scanned_likelihood,
        "needs_ocr": needs_ocr,
        "quality_score": round(float(quality_score or 0.0), 4),
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
    }
    return {
        "total_pages": total_pages,
        "empty_pages": empty_pages,
        "image_count": image_count,
        "table_count": table_count,
        "scanned_likelihood": scanned_likelihood,
        "needs_ocr": needs_ocr,
        "quality_score": round(float(quality_score or 0.0), 4),
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "quality": quality,
    }


def _mark_fallback(parsed: ParsedDocument, used: bool, reason: str) -> None:
    hints = dict(parsed.metadata_hints or {})
    quality = dict(hints.get("quality") or {})
    hints["fallback_used"] = used
    hints["fallback_reason"] = reason
    quality["fallback_used"] = used
    quality["fallback_reason"] = reason
    hints["quality"] = quality
    parsed.metadata_hints = hints


def _mark_pdf_parser_config(
    parsed: ParsedDocument,
    mode: str,
    mineru_parse_books: Optional[bool] = None,
    mineru_parser: Optional[DocumentParser] = None,
    plan: Optional[ParsePlan] = None,
) -> None:
    if not (parsed.parser_type or "").startswith("pdf:"):
        return
    hints = dict(parsed.metadata_hints or {})
    quality = dict(hints.get("quality") or {})
    command = getattr(mineru_parser, "command_name", getattr(Config, "MINERU_COMMAND", ""))
    backend = getattr(mineru_parser, "backend", getattr(Config, "MINERU_BACKEND", "pipeline"))
    method = getattr(mineru_parser, "method", getattr(Config, "MINERU_METHOD", "auto"))
    timeout_seconds = int(
        getattr(mineru_parser, "timeout_seconds", getattr(Config, "MINERU_TIMEOUT_SECONDS", 1800)) or 1800
    )
    parse_books = _to_bool(mineru_parse_books if mineru_parse_books is not None else getattr(Config, "MINERU_PARSE_BOOKS", False))
    hints["pdf_parser_mode"] = mode
    hints["mineru_command"] = command
    hints["mineru_backend"] = backend
    hints["mineru_method"] = method
    hints["mineru_timeout_seconds"] = timeout_seconds
    hints["mineru_parse_books"] = parse_books
    hints["parser_output_schema_version"] = PARSER_OUTPUT_SCHEMA_VERSION
    if plan:
        hints["parse_plan_type"] = plan.plan_type
        hints["parse_plan_reason"] = plan.reason
        hints["base_parser"] = plan.base_parser
        hints["advanced_parser"] = plan.advanced_parser
        hints["selective_enabled"] = plan.plan_type == "pymupdf_plus_mineru_selective"
        hints["selective_pages"] = plan.selected_pages
        hints["selective_page_count"] = len(plan.selected_pages)
        hints["selected_page_reasons"] = _selected_page_reasons(plan)
        for key, value in (plan.config_snapshot or {}).items():
            hints[key] = value
    quality["pdf_parser_mode"] = mode
    quality["mineru_command"] = command
    quality["mineru_backend"] = backend
    quality["mineru_method"] = method
    quality["mineru_timeout_seconds"] = timeout_seconds
    quality["mineru_parse_books"] = parse_books
    quality["parser_output_schema_version"] = PARSER_OUTPUT_SCHEMA_VERSION
    if plan:
        quality["parse_plan_type"] = plan.plan_type
        quality["parse_plan_reason"] = plan.reason
        quality["base_parser"] = plan.base_parser
        quality["advanced_parser"] = plan.advanced_parser
        quality["selective_enabled"] = plan.plan_type == "pymupdf_plus_mineru_selective"
        quality["selective_pages"] = plan.selected_pages
        quality["selective_page_count"] = len(plan.selected_pages)
        quality["selected_page_reasons"] = _selected_page_reasons(plan)
        for key, value in (plan.config_snapshot or {}).items():
            quality[key] = value
    hints["quality"] = quality
    parsed.metadata_hints = hints


def _log_pdf_quality(parsed: ParsedDocument) -> None:
    hints = parsed.metadata_hints or {}
    quality = hints.get("quality") or hints
    print(
        "[PdfParserQuality] "
        f"parser={parsed.parser_type} "
        f"pages={quality.get('total_pages', hints.get('total_pages', 0))} "
        f"chars={quality.get('total_chars', parsed.extracted_char_count)} "
        f"images={quality.get('image_count', hints.get('image_count', 0))} "
        f"tables={quality.get('table_count', hints.get('table_count', 0))} "
        f"needs_ocr={str(quality.get('needs_ocr', parsed.extraction_status == 'NEEDS_OCR')).lower()} "
        f"quality_score={quality.get('quality_score', parsed.extraction_quality)}"
    )


def _log_reason(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:240]


def _tail(value: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[-limit:]


def _format_command_for_log(cmd: List[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in cmd)


def _safe_pdf_page_count(file_path: str) -> int:
    try:
        doc = fitz.open(file_path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


def _normalize_markdown_text(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{4,}", "\n\n\n", normalized)
    return normalized.strip()


def _sections_from_markdown_pages(text: str) -> List[ParsedSection]:
    if not text.strip():
        return []
    page_pattern = re.compile(r"(?im)^\s*(?:#{1,3}\s*)?(?:page|p\.?)\s*[:#-]?\s*(\d+)\s*$")
    matches = list(page_pattern.finditer(text))
    if not matches:
        return [ParsedSection(text=text.strip(), location="mineru:markdown")]

    sections: List[ParsedSection] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        page_text = text[start:end].strip()
        if not page_text:
            continue
        page = int(match.group(1))
        sections.append(ParsedSection(text=page_text, page=page, location=f"page:{page}"))
    return sections


def _sections_from_mineru_json(data: Any) -> tuple[List[ParsedSection], int, int]:
    blocks = list(_iter_json_blocks(data))
    grouped: Dict[int, List[str]] = {}
    image_count = 0
    table_count = 0

    for block in blocks:
        block_type = str(block.get("type") or block.get("category") or block.get("block_type") or "").lower()
        page = _block_page_number(block)
        text = _block_text(block)
        if "table" in block_type:
            table_count += 1
            text = text or "[Table placeholder: table structure detected; no interpretation performed.]"
        elif any(token in block_type for token in ("image", "figure", "chart")):
            image_count += 1
            caption = text or block.get("caption") or block.get("img_caption") or ""
            text = f"[Figure/Image placeholder: {caption}; no visual interpretation performed.]".strip()
        elif any(token in block_type for token in ("title", "heading", "header")) and text:
            text = f"## {text}"

        text = _normalize_markdown_text(text)
        if not text:
            continue
        grouped.setdefault(page, []).append(text)

    sections = [
        ParsedSection(text="\n\n".join(parts), page=page or None, location=f"page:{page}" if page else "mineru:json")
        for page, parts in sorted(grouped.items(), key=lambda item: item[0])
        if parts
    ]
    return sections, image_count, table_count


def _iter_json_blocks(value: Any):
    if isinstance(value, dict):
        if any(key in value for key in ("text", "content", "html", "type", "category", "block_type")):
            yield value
        for child in value.values():
            yield from _iter_json_blocks(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_blocks(item)


def _block_text(block: Dict[str, Any]) -> str:
    for key in ("text", "content", "md", "markdown", "html", "caption"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return _html_to_text(value) if key == "html" else value.strip()
    return ""


def _block_page_number(block: Dict[str, Any]) -> int:
    for key in ("page", "page_no", "page_number", "page_idx"):
        if key not in block:
            continue
        try:
            value = int(block[key])
            return value + 1 if key == "page_idx" and value >= 0 else value
        except (TypeError, ValueError):
            continue
    return 0


def _status_from_sections(sections: List[ParsedSection], total_pages: int) -> tuple[str, float]:
    if not sections:
        return "EMPTY_DOCUMENT", 0.0
    if total_pages <= 0:
        return "CHUNKED", 1.0
    covered_pages = len({section.page for section in sections if section.page})
    quality = min(1.0, covered_pages / max(1, total_pages)) if covered_pages else 1.0
    return ("PARTIAL_TEXT" if quality < 0.8 else "CHUNKED"), quality


def _estimate_table_like_blocks(text: str) -> int:
    count = 0
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        separators = stripped.count("|") + stripped.count("\t")
        digit_ratio = sum(ch.isdigit() for ch in stripped) / max(1, len(stripped))
        if separators >= 2 or digit_ratio > 0.45:
            count += 1
    return count


def _count_markdown_placeholders(text: str, token: str) -> int:
    return len(re.findall(token, text or "", flags=re.IGNORECASE))


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        text = html.unescape(data or "").strip()
        if text:
            self.parts.append(text)


def _html_to_text(raw_html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(raw_html)
    text = "\n".join(extractor.parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _first_non_empty_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return ""


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag
