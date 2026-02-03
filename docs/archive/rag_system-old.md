# Kaia RAG System Documentation

## Overview
The Retrieval-Augmented Generation (RAG) system is the core of Kaia's long-term memory. It allows her to recall past interactions, access uploaded documents, and maintain a consistent persona.

## Architecture

### 1. Ingestion Pipeline
The ingestion pipeline handles the processing of new files in the `knowledge_base/` directory.
- **File Detection**: Scans for new or modified files (`.txt`, `.md`, `.pdf`, `.docx`).
- **Text Extraction**: Converts PDFs and DOCX files to Markdown.
- **Chunking**: Splits text into manageable chunks (default 1024 tokens) with overlap.
- **Embedding**: Generates vector embeddings using `nomic-embed-text`.
- **Indexing**: Stores embeddings in a local vector store (`memory/`).

### 2. Smart Fiction Filter
To prevent hallucinations from contaminating the knowledge base, a **Smart Fiction Filter** is applied during ingestion.
- **Purpose**: Blocks specific fictional story patterns (e.g., "server farm on Titan", "memory leak in '21") that the LLM might hallucinate and try to save as memory.
- **Mechanism**: Regex-based pattern matching runs on new content *before* it is indexed.
- **Safety**: Unlike aggressive filters, this **does not** block real user names or general conversation, ensuring legitimate memories are preserved.

### 3. Retrieval
When a user queries Kaia:
- **Hybrid Search**: Combines vector similarity search with BM25 keyword search.
- **Reranking**: Results are reranked based on relevance and recency.
- **Source Filtering**: Identity queries ("Who am I?") are restricted to `user_logs` and `user_profiles` to prevent hallucinations.

### 4. Hallucination Detector
A runtime `HallucinationDetector` checks generated responses *before* they are sent to the user or logged.
- **Detection**: Scans for known hallucination keywords (e.g., "Juanita", "Deane").
- **Action**: If detected, the response is cleaned or replaced with a fallback to prevent the hallucination from entering the feedback loop.
