# RAG Evaluation Comparison

- Run date: 2026-04-03
- Source document: `examples/sample-report.pdf`
- Pipeline: `parser.py` -> `chunker.py` -> `embedder.py` -> `rag2.py`
- Customer ID used for retrieval: `rag-eval-sample-report`
- Chunks stored in Chroma: 76
- RAG model in `rag2.py`: `llama-3.3-70b-versatile`
- Notes: this rerun used the updated API key and completed without the earlier Groq rate-limit failure.

## Summary

- Match: 16
- Partial: 5
- Miss/Wrong: 6

## Results

### Q1
Question: What percentage of training data comes from CommonCrawl?

Expected: 67%

Model answer: According to [DOC-5] (dated 2026-04-03T17:45:55.736357+00:00), the training data from CommonCrawl represents 67.0% of the total training data.

Conflict summary: None.

Verdict: Match

Comparison note: Correct value.

Top retrieved source: `sample-report.pdf`, page 7, heading `Page 7`

### Q2
Question: How many tokens were used to train LLaMA models?

Expected: ~1T tokens (smaller models) and ~1.4T tokens (larger models)

Model answer: According to [DOC-2] (dated 2026-04-03T17:45:55.736357+00:00), the LLaMA-33B and LLaMA-65B models were trained on 1.4T tokens, while the smaller models were trained on 1.0T tokens.

Additionally, [DOC-3] (dated 2026-04-03T17:45:55.736357+00:00) mentions that the models were trained on trillions of tokens.

Therefore, the number of tokens used to train LLaMA models is 1.0T to 1.4T tokens, depending on the model size.

No conflict detected.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 6, heading `Page 6`

### Q3
Question: What optimizer is used?

Expected: AdamW (beta1 = 0.9, beta2 = 0.95)

Model answer: I don't have enough information in your documents to answer this.

Verdict: Miss/Wrong

Comparison note: Failed to answer.

Top retrieved source: `sample-report.pdf`, page 7, heading `Page 7`

### Q4
Question: What is the batch size used during training?

Expected: 4M tokens

Model answer: The batch size used during training is 4M tokens, as stated in [DOC-1] (dated 2026-04-03) and [DOC-3] (dated 2026-04-03).

Conflict summary: There is no conflict in the provided documents regarding the batch size used during training. All relevant sources, [DOC-1] and [DOC-3], state the same batch size of 4M tokens.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 3, heading `Page 3`

### Q5
Question: What percentage of data comes from C4?

Expected: 15%

Model answer: According to [DOC-2] (dated 2026-04-03), the percentage of data that comes from C4 is 15.0%.

Conflict summary: There is no conflict detected in the provided context regarding the percentage of data from C4. [DOC-2] (dated 2026-04-03) states that C4 represents 15.0% of the data.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 10, heading `Page 10`

### Q6
Question: Which dataset has the smallest proportion?

Expected: StackExchange (2%)

Model answer: According to [DOC-1] (dated 2026-04-03), the dataset with the smallest proportion is ArXiv with 2.5% and StackExchange with 2.0%.

Conflict summary: None.

Verdict: Partial

Comparison note: Includes the correct dataset but also incorrectly names ArXiv.

Top retrieved source: `sample-report.pdf`, page 2, heading `Page 2`

### Q7
Question: What is the disk size of CommonCrawl data?

Expected: ~3.3 TB

Model answer: The disk size of CommonCrawl data is 3.3 TB, as stated in [DOC-1] (dated 2026-04-03).

There is no conflicting information in the provided context.

Conflict summary: None.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 2, heading `Page 2`

### Q8
Question: How many layers does the 65B model have?

Expected: 80 layers

Model answer: According to [DOC-1] (dated 2026-04-03), the 65.2B model has 80 layers.

Conflict summary: None.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 3, heading `Page 3`

### Q9
Question: Why does LLaMA prefer smaller models trained longer?

Expected: Because inference cost matters; smaller models trained on more tokens can achieve similar performance but are cheaper at inference.

Model answer: According to [DOC-4] (dated 2026-04-03), LLaMA prefers smaller models trained longer because "a smaller one trained longer will ultimately be cheaper at inference." This is stated in the abstract of the report.

Conflict summary: There is no conflict detected in the provided context regarding this question. [DOC-4] (dated 2026-04-03) states that smaller models trained longer are preferred due to cheaper inference costs.

Verdict: Partial

Comparison note: Gets the inference-cost reason right but omits the similar-performance framing.

Top retrieved source: `sample-report.pdf`, page 6, heading `Page 6`

### Q10
Question: What scaling law influences LLaMA’s design?

Expected: Chinchilla scaling laws (optimize data vs parameters for compute efficiency)

Model answer: The scaling law from Hoffmann et al. (2022) influences LLaMA's design, which determines how to best scale the dataset and model sizes for a particular training compute budget [DOC-4, dated 2026-04-03]. However, this objective disregards the inference budget, which becomes critical when serving a language model at scale [DOC-4, dated 2026-04-03].

Given a target level of performance, the preferred model is not the fastest to train but the fastest at inference [DOC-4, dated 2026-04-03].

Conflict summary: There is no conflict in the provided documents regarding the scaling law that influences LLaMA's design. [DOC-4] (dated 2026-04-03) states that the scaling law from Hoffmann et al. (2022) influences LLaMA's design.

Verdict: Partial

Comparison note: Correct idea, but it names Hoffmann et al. (2022) instead of explicitly saying Chinchilla scaling laws.

Top retrieved source: `sample-report.pdf`, page 6, heading `Page 6`

### Q11
Question: What normalization technique is used?

Expected: RMSNorm (pre-normalization)

Model answer: The normalization technique used is lowercasing generated answers, removing articles, punctuation, and duplicate whitespaces [DOC-3, dated 2026-04-03].

Conflict summary: There is no conflict detected in the provided context regarding the normalization technique used.

Verdict: Miss/Wrong

Comparison note: Incorrectly answered with evaluation normalization instead of model architecture normalization.

Top retrieved source: `sample-report.pdf`, page 16, heading `Page 16`

### Q12
Question: What replaces ReLU?

Expected: SwiGLU activation

Model answer: The SwiGLU activation function replaces the ReLU non-linearity, as stated in [DOC-1] (dated 2026-04-03) and [DOC-4] (dated 2026-04-03). According to [DOC-1], "We replace the ReLU non-linearity by the SwiGLU activation function, introduced by Shazeer (2020) to improve the performance."

Conflict summary: There is no conflict detected in the provided documents regarding this question. [DOC-1] (dated 2026-04-03) and [DOC-4] (dated 2026-04-03) both state that SwiGLU replaces ReLU.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 3, heading `Page 3`

### Q13
Question: What replaces absolute positional embeddings?

Expected: Rotary positional embeddings (RoPE)

Model answer: According to [DOC-1] (dated 2026-04-03), rotary positional embeddings (RoPE) replace absolute positional embeddings. As stated in [DOC-1], "We remove the absolute positional embeddings, and instead, add rotary positional embeddings (RoPE), introduced by Su et al. (2021), at each layer of the network."

Conflict summary: There is no conflict detected in the provided documents regarding this question. [DOC-1] (dated 2026-04-03) clearly states that rotary positional embeddings replace absolute positional embeddings.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 3, heading `Page 3`

### Q14
Question: Does LLaMA-13B outperform GPT-3?

Expected: Yes, on most benchmarks despite being ~10x smaller

Model answer: According to [DOC-3] (dated 2026-04-03), LLaMA-13B outperforms GPT-3 (175B) on most benchmarks, despite being 10× smaller.

Conflict summary: [DOC-3] (dated 2026-04-03) states that LLaMA-13B outperforms GPT-3 on most benchmarks. There are no conflicting sources provided.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 6, heading `Page 6`

### Q15
Question: Which benchmark shows unstable performance?

Expected: SIQA

Model answer: According to [DOC-2] (dated 2026-04-03T17:45:55.736357+00:00), the WinoGrande benchmark shows unstable performance, as it is stated that "On WinoGrande, the performance does not correlate as well with training perplexity: the LLaMA-33B and LLaMA-65B have similar performance during the training."

Conflict summary: [DOC-2] (dated 2026-04-03T17:45:55.736357+00:00) states that WinoGrande shows unstable performance. There is no conflicting information in the provided documents.

Verdict: Miss/Wrong

Comparison note: Wrong benchmark.

Top retrieved source: `sample-report.pdf`, page 5, heading `Page 5`

### Q16
Question: Which benchmark does not correlate well with scaling?

Expected: WinoGrande

Model answer: I don't have enough information in your documents to answer this question.

Verdict: Miss/Wrong

Comparison note: Failed to answer.

Top retrieved source: `sample-report.pdf`, page 5, heading `Page 5`

### Q17
Question: What learning rate is used for 65B?

Expected: 1.5e-4

Model answer: The learning rate used for the 65.2B model is 1.5e−4 [DOC-3], dated 2026-04-03.

This information is found in Table 2 of the document, which lists the model sizes, architectures, and optimization hyper-parameters.

There is no conflict detected in the provided context regarding the learning rate for the 65B model.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 7, heading `Page 7`

### Q18
Question: How many GPUs were used to train the 65B model?

Expected: ~2048 A100 GPUs

Model answer: According to [DOC-1] (dated 2026-04-03), when training a 65B-parameter model, the code processes around 380 tokens/sec/GPU on 2048 A100 GPU with 80GB of RAM.

Therefore, 2048 GPUs were used to train the 65B model.

Conflict summary: There is no conflict in the provided documents regarding the number of GPUs used to train the 65B model. [DOC-1] (dated 2026-04-03) states that 2048 A100 GPUs with 80GB of RAM were used.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 4, heading `Page 4`

### Q19
Question: How long did training take?

Expected: ~21 days

Model answer: I don't have enough information in your documents to answer this. The provided context does not mention the duration of the training process.

Verdict: Miss/Wrong

Comparison note: Failed to answer.

Top retrieved source: `sample-report.pdf`, page 3, heading `Page 3`

### Q20
Question: What happens to toxicity as model size increases?

Expected: It increases

Model answer: According to [DOC-1] (dated 2026-04-03), the relation between toxicity and model size may only apply within a model family. [DOC-4] (dated 2026-04-03) also reports that toxicity scores increase with the size of the model, especially for respectful prompts. However, [DOC-1] mentions that Hoffmann et al. (2022) do not see a difference between Chinchilla and Gopher, despite different sizes.

CONFLICT DETECTED: [DOC-1] and [DOC-4] suggest a positive correlation between model size and toxicity, while [DOC-1] also references Hoffmann et al. (2022) which does not observe this correlation.

[TRUST-1] is [DOC-4] (dated 2026-04-03), which states: "These scores are “comparable” with what we observe in the literature... with the notable exception of Hoffmann et al. (2022) where they do not". [CONFLICT-1] is also [DOC-1] (dated 2026-04-03), which mentions that Hoffmann et al. (2022) do not see a difference between Chinchilla and Gopher.

Conflict summary: [DOC-4] (dated 2026-04-03) states that toxicity scores increase with model size. [DOC-1] (dated 2026-04-03) states that Hoffmann et al. (2022) do not see a difference in toxicity between models of different sizes. Relying on [DOC-4] as it provides more direct evidence of the relationship between model size and toxicity.

Verdict: Match

Comparison note: Final answer aligns with the expected answer, though it adds caveats.

Top retrieved source: `sample-report.pdf`, page 8, heading `Page 8`

### Q21
Question: Which bias category is highest in CrowS-Pairs?

Expected: Religion

Model answer: According to [DOC-1] (dated 2026-04-03T17:45:55.736357+00:00), the highest bias category in CrowS-Pairs is religion, with LLaMA being 10% more biased than OPT-175B in this category.

Conflict summary: There is no conflicting information in the provided documents regarding the highest bias category in CrowS-Pairs. [DOC-1] (dated 2026-04-03T17:45:55.736357+00:00) states that the religion category has the highest bias.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 9, heading `Page 9`

### Q22
Question: What is TruthfulQA measuring?

Expected: Model’s ability to generate truthful (non-hallucinated) answers

Model answer: According to [DOC-1] (dated 2026-04-03), TruthfulQA measures "the truthfulness of a model, i.e., its ability to identify when a claim is true" in the sense of "literal truth about the real world".

Conflict summary: There is no conflict detected in the provided context regarding the measurement of TruthfulQA. [DOC-1] (dated 2026-04-03) states that TruthfulQA measures the truthfulness of a model.

Verdict: Match

Comparison note: Good enough semantically.

Top retrieved source: `sample-report.pdf`, page 9, heading `Page 9`

### Q23
Question: Where does LLaMA underperform compared to PaLM/Chinchilla?

Expected: MMLU (due to less book/academic data)

Model answer: According to [DOC-1] (dated 2026-04-03), LLaMA-65B underperforms PaLM-540B and Chinchilla-70B by a few percent in average, and across most domains, specifically on BoolQ and WinoGrande.

Conflict summary: [DOC-1] (dated 2026-04-03) states that LLaMA-65B underperforms PaLM-540B and Chinchilla-70B on BoolQ and WinoGrande. [DOC-5] (dated 2026-04-03) also mentions that LLaMA-65B outperforms Chinchilla-70B on all reported benchmarks but BoolQ. Relying on [DOC-1] as it provides more specific information about the underperformance.

Verdict: Miss/Wrong

Comparison note: Wrong benchmark and misses the expected MMLU explanation.

Top retrieved source: `sample-report.pdf`, page 6, heading `Page 6`

### Q24
Question: Why might LLaMA be weaker on knowledge-heavy tasks?

Expected: Limited training data from books and academic sources (~177GB only)

Model answer: According to [DOC-1] (dated 2026-04-03), LLaMA might be weaker on knowledge-heavy tasks because it was trained on a limited amount of books and academic papers, totaling only 177GB, whereas other models like Gopher, Chinchilla, and PaLM were trained on up to 2TB of books. This limited training data may not provide enough knowledge for LLaMA to perform well on tasks that require a large amount of knowledge.

Conflict summary: None.

Verdict: Match

Comparison note: Correct.

Top retrieved source: `sample-report.pdf`, page 6, heading `Page 6`

### Q25
Question: List all training datasets used.

Expected: CommonCrawl; C4; GitHub; Wikipedia; Books (Gutenberg + Books3); ArXiv; StackExchange

Model answer: The training datasets used are:

1. CommonCrawl (67%) [DOC-1, dated 2026-04-03]
2. C4 (15%) [DOC-1, dated 2026-04-03]
3. Github (4.5%) [DOC-1, dated 2026-04-03]
4. Wikipedia (4.5%) [DOC-1, dated 2026-04-03]
5. Books (4.5%) [DOC-1, dated 2026-04-03]
6. ArXiv (2.5%) [DOC-1, dated 2026-04-03]
7. StackExchange (2%) [DOC-1, dated 2026-04-03]

Note: The percentages in parentheses represent the proportion of each dataset in the training set.

Conflict summary: There are no conflicting sources in the provided context regarding the list of training datasets. [DOC-1] (dated 2026-04-03) states the list of datasets used for training.

Verdict: Match

Comparison note: Correct dataset list.

Top retrieved source: `sample-report.pdf`, page 2, heading `Page 2`

### Q26
Question: Why can LLaMA run on a single GPU?

Expected: Because smaller variants (e.g., 13B) are optimized for inference efficiency

Model answer: According to [DOC-5] (dated 2026-04-03), some of the LLaMA models are relatively small and can be run on a single GPU.

Conflict summary: There is no conflict in the provided documents regarding this question. [DOC-5] (dated 2026-04-03) states that some LLaMA models can be run on a single GPU.

Verdict: Partial

Comparison note: Gets the small-model point but not the inference-efficiency rationale.

Top retrieved source: `sample-report.pdf`, page 11, heading `Page 11`

### Q27
Question: What key idea enables LLaMA to beat larger models?

Expected: Training on more tokens with compute-optimal scaling instead of just increasing parameters

Model answer: The key idea that enables LLaMA to beat larger models is that it is possible to train state-of-the-art models using publicly available datasets exclusively, without resorting to proprietary and inaccessible datasets, and by training on more tokens than what is typically used [DOC-4, dated 2026-04-03]. This approach allows LLaMA to achieve competitive performance with the best existing LLMs, despite being smaller in size.

Conflict summary: None.

Verdict: Partial

Comparison note: Captures the more-tokens idea but misses the compute-optimal scaling emphasis.

Top retrieved source: `sample-report.pdf`, page 6, heading `Page 6`
