# Kaia RAG System Documentation

## Overview
The Retrieval-Augmented Generation (RAG) system is the core of Kaia's long-term memory. It allows her to recall past interactions, access uploaded documents, and maintain a consistent persona.

## Architecture

### 1. Ingestion Pipeline
The ingestion pipeline handles the processing of new files in the `knowledge_base/` directory.
- **File Detection**: Scans for new or modified files (`.txt`, `.md`, `.pdf`, `.docx`).
- **Text Extraction**: Converts PDFs and DOCX files to Markdown.
- **Chunking**: Splits text into configurable chunks (`config.rag_node_chunk_size`, default 1024 tokens) with overlap (`config.rag_node_chunk_overlap`, default 200 tokens).
- **Embedding**: Generates vector embeddings using `nomic-embed-text` on **CPU** (`num_gpu: 0`, `num_thread: 4`). Zero GPU impact.
- **Indexing**: Stores embeddings in a unified path: `memory/rag_storage/` (consolidated from legacy `./storage` split).

### 2. Smart Fiction Filter
To prevent hallucinations from contaminating the knowledge base, a **Smart Fiction Filter** is applied during ingestion.
- **Purpose**: Blocks specific fictional story patterns (e.g., "server farm on Titan", "memory leak in '21") that the LLM might hallucinate and try to save as memory.
- **Mechanism**: Regex-based pattern matching runs on new content *before* it is indexed.
- **Safety**: Unlike aggressive filters, this **does not** block real user names or general conversation, ensuring legitimate memories are preserved.

### 3. Retrieval
When a user queries Kaia:
- **Hierarchical Retrieval**: Intent-aware routing selects which index types to search (persona, user_profiles, user_logs, knowledge, dreams, news).
- **Hybrid Search**: Combines vector similarity search with BM25 keyword search using **Reciprocal Rank Fusion (RRF)**.
- **Dynamic Scoring**: Results are scored with configurable boosts for source type (persona, profiles, dreams) and recency.
- **Source Filtering**: Identity queries ("Who am I?") are restricted to `user_logs` and `user_profiles` to prevent hallucinations.
- **Timeout Guard**: Retrieval is wrapped in `config.rag_retrieval_timeout` (default 30s). Parallel gather uses 2x timeout (60s). On timeout, partial results are collected gracefully.

### 4. Hallucination Detector
A runtime `HallucinationDetector` checks generated responses *before* they are sent to the user or logged.
- **Detection**: Scans for known hallucination keywords (e.g., "Juanita", "Deane").
- **Hazy Memory**: Detects "hazy memory" admissions to gracefully handle retrieval gaps.
- **Action**: If detected, the response is cleaned or replaced with a fallback to prevent the hallucination from entering the feedback loop.

### 5. Knowledge Boundary
The `KnowledgeBoundary` system prevents Kaia from fabricating information about entities she doesn't know.
- **Entity Extraction**: Identifies named entities in user queries via capitalization and acronym patterns.
- **Fuzzy Matching**: Levenshtein-distance matching with a performance guard to skip large contexts.
- **Boundary Response**: When unknown entities are detected, generates an honest "I don't know" response.
- See [Intelligence Layer](intelligence-layer.md#6-knowledge-boundary) for details.

### 6. Dream Engine Integration
Dreams (nightly 3-5 AM reflections) are stored as RAG nodes in the `dreams` index type.
- Dreams are given a configurable retrieval boost (`config.rag_boost_dreams`, default 0.1).
- Intent routing for `DREAM_RECALL` strategies specifically targets the dreams index.
