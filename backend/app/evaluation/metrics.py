import re
from typing import List, Dict, Any, Set


class RAGMetricsEvaluator:
    """Computes standard enterprise RAG evaluation metrics."""

    @staticmethod
    def _stem(word: str) -> str:
        """Lightweight suffix stemmer for morphological alignment."""
        word = word.lower().strip()
        for suffix in ("tions", "tion", "ments", "ment", "ing", "ies", "ied", "ed", "es", "s"):
            if len(word) > len(suffix) + 3 and word.endswith(suffix):
                return word[:-len(suffix)]
        return word

    @classmethod
    def _tokenize(cls, text: str, stem: bool = False) -> Set[str]:
        """Normalize and tokenize text into unique content tokens (lowercased, alphanumeric)."""
        stopwords = {
            "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
            "which", "this", "that", "these", "those", "then", "just", "so", "than",
            "such", "both", "through", "about", "for", "is", "of", "while", "during",
            "to", "from", "in", "out", "on", "off", "again", "further", "then", "once",
            "here", "there", "when", "where", "why", "how", "all", "any", "both",
            "each", "few", "more", "most", "other", "some", "such", "no", "nor",
            "not", "only", "own", "same", "so", "than", "too", "very", "can", "will",
            "just", "don", "should", "now", "be", "been", "being", "have", "has", "had",
            "having", "do", "does", "did", "doing", "are", "was", "were", "must", "with",
            "at", "by", "under", "per"
        }
        tokens = re.findall(r"\b[a-zA-Z0-9_\-]+\b", text.lower())
        result = set()
        for t in tokens:
            if t not in stopwords and len(t) > 1:
                result.add(cls._stem(t) if stem else t)
        return result

    @classmethod
    def calculate_faithfulness(cls, answer: str, contexts: List[str]) -> float:
        """Calculate faithfulness/groundedness score in [0.0, 1.0].
        
        Evaluates whether claims in the generated answer are supported by retrieved contexts.
        """
        if not answer.strip():
            return 0.0
        if not contexts:
            return 0.0

        # Segment answer into sentences/clauses
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", answer)
            if len(s.strip()) > 5
        ]
        if not sentences:
            return 0.0

        combined_context = " ".join(contexts).lower()
        context_tokens = cls._tokenize(combined_context, stem=True)
        numbers_in_context = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", combined_context))

        supported_count = 0
        for sentence in sentences:
            # Strip citation brackets e.g. [1], [2] BEFORE extracting tokens and numbers
            clean_sentence = re.sub(r"\[\d+\]", "", sentence).strip()
            sentence_tokens = cls._tokenize(clean_sentence, stem=True)
            if not sentence_tokens:
                supported_count += 1
                continue

            # Check token overlap
            overlap = sentence_tokens.intersection(context_tokens)
            overlap_ratio = len(overlap) / len(sentence_tokens)

            # Check numbers in clean sentence
            numbers_in_sentence = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", clean_sentence))
            numbers_supported = (
                not numbers_in_sentence or
                len(numbers_in_sentence.intersection(numbers_in_context)) >= len(numbers_in_sentence)
            )

            if overlap_ratio >= 0.40 and numbers_supported:
                supported_count += 1

        return round(supported_count / len(sentences), 4)

    @classmethod
    def calculate_answer_relevance(cls, query: str, answer: str) -> float:
        """Calculate answer relevance score in [0.0, 1.0].
        
        Evaluates how pertinent the answer is to the user's inquiry.
        """
        if not query.strip() or not answer.strip():
            return 0.0

        query_tokens = cls._tokenize(query, stem=True)
        answer_tokens = cls._tokenize(answer, stem=True)

        if not query_tokens:
            return 1.0

        # Check for non-answers or generic refusals
        refusal_patterns = [
            "i don't know", "i cannot answer", "information not provided",
            "no relevant documents", "not mentioned in the context"
        ]
        is_refusal = any(p in answer.lower() for p in refusal_patterns)
        if is_refusal:
            return 0.25

        # Lexical recall of stemmed query terms in answer
        overlap = query_tokens.intersection(answer_tokens)
        if not overlap:
            return 0.0

        query_coverage = len(overlap) / len(query_tokens)
        # Direct concise answers naturally cover key query concepts (typically 40-60% of all query words)
        effective_coverage = min(1.0, query_coverage / 0.45)

        # Substance factor based on answer length
        substance_score = min(1.0, len(answer.split()) / 10.0)
        relevance = (effective_coverage * 0.75) + (substance_score * 0.25)
        return round(min(1.0, relevance), 4)

    @classmethod
    def calculate_context_precision(
        cls, retrieved_contexts: List[str], ground_truth_contexts: List[str]
    ) -> float:
        """Calculate Context Precision (Mean Average Precision @ K) in [0.0, 1.0].
        
        Evaluates whether relevant chunks are ranked at the top of the retrieved list.
        """
        if not retrieved_contexts or not ground_truth_contexts:
            return 0.0

        gt_token_sets = [cls._tokenize(gt, stem=True) for gt in ground_truth_contexts if gt.strip()]
        if not gt_token_sets:
            return 0.0

        relevant_flags: List[bool] = []
        for ctx in retrieved_contexts:
            ctx_tokens = cls._tokenize(ctx, stem=True)
            is_rel = any(
                len(ctx_tokens.intersection(gt_set)) / max(len(gt_set), 1) >= 0.35
                for gt_set in gt_token_sets
            )
            relevant_flags.append(is_rel)

        total_relevant = sum(relevant_flags)
        if total_relevant == 0:
            return 0.0

        running_hits = 0
        precision_sum = 0.0
        for k, is_rel in enumerate(relevant_flags, start=1):
            if is_rel:
                running_hits += 1
                precision_at_k = running_hits / k
                precision_sum += precision_at_k

        return round(precision_sum / total_relevant, 4)

    @classmethod
    def calculate_context_recall(
        cls, retrieved_contexts: List[str], ground_truth_contexts: List[str]
    ) -> float:
        """Calculate Context Recall in [0.0, 1.0].
        
        Evaluates the proportion of ground-truth context facts captured in the retrieved chunks.
        """
        if not ground_truth_contexts:
            return 1.0
        if not retrieved_contexts:
            return 0.0

        retrieved_combined = " ".join(retrieved_contexts)
        retrieved_tokens = cls._tokenize(retrieved_combined, stem=True)

        captured_count = 0
        for gt in ground_truth_contexts:
            gt_tokens = cls._tokenize(gt, stem=True)
            if not gt_tokens:
                captured_count += 1
                continue
            overlap = gt_tokens.intersection(retrieved_tokens)
            if len(overlap) / len(gt_tokens) >= 0.40:
                captured_count += 1

        return round(captured_count / len(ground_truth_contexts), 4)

    @classmethod
    def calculate_citation_accuracy(
        cls, answer: str, retrieved_contexts: List[str], citations: List[Dict[str, Any]] = None
    ) -> float:
        """Calculate Citation Accuracy in [0.0, 1.0].
        
        Verifies that [1], [2] citations correspond to existing chunks and corroborate the cited claim.
        """
        matches = list(re.finditer(r"\[(\d+)\]", answer))
        if not matches:
            return 0.0 if retrieved_contexts else 1.0

        total_citations = len(matches)
        valid_citations = 0

        for match in matches:
            citation_num = int(match.group(1))
            if 1 <= citation_num <= len(retrieved_contexts):
                target_context = retrieved_contexts[citation_num - 1]
                target_tokens = cls._tokenize(target_context, stem=True)

                start_pos = max(0, match.start() - 120)
                preceding_text = answer[start_pos:match.start()]
                claim_tokens = cls._tokenize(preceding_text, stem=True)

                if claim_tokens:
                    overlap = claim_tokens.intersection(target_tokens)
                    if len(overlap) / len(claim_tokens) >= 0.20:
                        valid_citations += 1
                    else:
                        valid_citations += 0.5
                else:
                    valid_citations += 1

        return round(valid_citations / total_citations, 4)
