import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from app.config import settings
from app.prompts.summary_prompt import (
    FAITHFUL_SUMMARY_SYSTEM_PROMPT,
    CHUNK_SUMMARY_SYSTEM_PROMPT,
    COMBINE_SUMMARIES_SYSTEM_PROMPT,
    build_direct_summary_prompt,
    build_chunk_summary_prompt,
    build_combine_prompt
)
from app.schemas.note_schema import SummaryResponse, SummaryMetadata
from app.services.document_service import DocumentService, ExtractedDocument
from app.services.chapter_service import ChapterService
from app.services.chunking_service import ChunkingService
from app.services.nvidia_service import nvidia_service

logger = logging.getLogger(__name__)


class SummaryService:
    """
    Orchestrates the end-to-end document summarization workflow:
    - Text extraction (PDF / DOCX)
    - Chapter selection and validation
    - Adaptive chunking for large texts with bounded concurrent processing
    - Synthesis and metadata generation
    """

    PROVIDER_NAME: str = "nvidia"

    @classmethod
    async def process_document(
        cls,
        file_path: Path,
        original_filename: str,
        requested_chapters: Optional[List[str]] = None
    ) -> SummaryResponse:
        """
        Executes end-to-end document summarization.
        """
        logger.info("Starting processing for file: %s", original_filename)

        # Step 1: Extract document text
        document: ExtractedDocument = DocumentService.extract_text_from_file(
            file_path=file_path,
            original_filename=original_filename
        )

        # Step 2: Chapter selection branch
        relevant_text, found_chapters, is_full_doc = ChapterService.extract_requested_content(
            document=document,
            requested_chapters=requested_chapters
        )

        context_label = "Full Document" if is_full_doc else f"Chapters {', '.join(found_chapters)}"
        logger.info(
            "Selected text for %s: %d characters, %d words",
            context_label,
            len(relevant_text),
            len(relevant_text.split())
        )

        # Step 3 & 4: Check text size and summarize
        model_used = settings.nvidia_model

        if not ChunkingService.is_large_text(relevant_text):
            # Single pass summarization
            logger.info("Processing as single direct chunk (%d chars) via %s", len(relevant_text), cls.PROVIDER_NAME)
            summary_text = await nvidia_service.generate_chat_completion(
                system_prompt=FAITHFUL_SUMMARY_SYSTEM_PROMPT,
                user_prompt=build_direct_summary_prompt(relevant_text, context_label)
            )
            chunks_processed = 1
        else:
            # Multi-chunk processing for large documents with bounded concurrency
            chunks = ChunkingService.split_into_chunks(relevant_text)
            total_chunks = len(chunks)
            logger.info(
                "Text exceeds single chunk threshold. Split into %d chunks. Processing concurrently (max %d workers)...",
                total_chunks,
                settings.max_concurrent_chunk_requests
            )

            semaphore = asyncio.Semaphore(settings.max_concurrent_chunk_requests)

            async def process_single_chunk(idx: int, chunk: str) -> tuple[int, str]:
                async with semaphore:
                    logger.info("Processing chunk %d of %d", idx, total_chunks)
                    summary = await nvidia_service.generate_chat_completion(
                        system_prompt=CHUNK_SUMMARY_SYSTEM_PROMPT,
                        user_prompt=build_chunk_summary_prompt(chunk, idx, total_chunks)
                    )
                    return idx, summary

            # Run chunk summarization tasks concurrently
            tasks = [process_single_chunk(idx, chunk) for idx, chunk in enumerate(chunks, start=1)]
            indexed_results = await asyncio.gather(*tasks)

            # Sort by original index to ensure strict chronological order
            indexed_results.sort(key=lambda r: r[0])
            chunk_summaries = [r[1] for r in indexed_results]
            chunks_processed = total_chunks

            # Synthesize all chunk summaries into final master notes
            logger.info("Synthesizing %d chunk summaries into final notes via %s", len(chunk_summaries), cls.PROVIDER_NAME)
            summary_text = await nvidia_service.generate_chat_completion(
                system_prompt=COMBINE_SUMMARIES_SYSTEM_PROMPT,
                user_prompt=build_combine_prompt(chunk_summaries)
            )

        # Step 5: Construct Pydantic-validated response
        metadata = SummaryMetadata(
            filename=original_filename,
            file_type=document.file_type,
            total_document_words=document.word_count,
            total_document_characters=document.char_count,
            processed_words=len(relevant_text.split()),
            processed_characters=len(relevant_text),
            chapters_requested=requested_chapters if requested_chapters else None,
            chapters_found=found_chapters,
            chunks_processed=chunks_processed,
            model_used=model_used,
            provider_used=cls.PROVIDER_NAME,
            is_full_document=is_full_doc
        )

        return SummaryResponse(
            success=True,
            summary=summary_text,
            metadata=metadata
        )
