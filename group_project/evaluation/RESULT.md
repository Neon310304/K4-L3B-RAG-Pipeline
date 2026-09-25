# RAG evaluation results

## Run information

| Field | Value |
| --- | --- |
| Evaluation date | 2026-09-25T06:18:32+00:00 |
| Framework and version | `src.evaluate_ab`, deterministic lexical metrics |
| Evaluator model | None; fixed token overlap evaluator |
| Generator model | None; fixed extractive generator shared by A/B |
| Embedding model | BAAI/bge-m3 @ `5617a9f61b028005a4858fdac845db406aefb181` |
| Corpus version/commit | `a23df34c17c930e95b755d250921f41969e25ee0`; uncommitted changes present (recorded source snapshot is corpus/chunk SHA); corpus SHA `c2f27eecf7515d01cfcd659154788810f38b6f7a8c7851b4fc6eb1b4171d47fa` |
| Golden dataset size | 17 |
| `top_k` | 5 |
| Fallback threshold and calibration | Production 0.60; A/B uses -1.0 to disable fallback and isolate retrieval strategy |

## Configurations

- **Config A — dense-only:** shared local BGE-M3 dense search, no BM25 and no RRF.
- **Config B — hybrid + RRF:** same dense search plus BM25 and one RRF pass (`k=60`).
- Both use the same corpus snapshot, deterministic extractive generator, evaluator, prompt `Answer only from retrieved context; do not add outside knowledge.`, and `top_k=5`. A/B does not call PageIndex.

## Overall scores

| Metric | Config A | Config B | Delta B−A |
| --- | ---: | ---: | ---: |
| Faithfulness | 1.0000 | 1.0000 | +0.0000 |
| Answer relevance | 0.0371 | 0.0365 | -0.0006 |
| Context recall | 0.7941 | 0.7941 | +0.0000 |
| Context precision | 0.1882 | 0.1882 | +0.0000 |
| **Average** | 0.5049 | 0.5047 | -0.0001 |

## A/B comparison

- Cấu hình có average cao hơn trong lần chạy này: **A dense-only**.
- Delta theo metric: faithfulness +0.0000, relevance -0.0006, recall +0.0000, precision +0.0000.
- Latency local: A 2.031s, B 2.145s trên cùng 17 query; chênh lệch B−A +0.114s. Cost API của cả hai là 0 trong evaluator offline.
- Faithfulness ở đây là containment proxy của extractive generator, không phải phán đoán LLM. Không dùng kết quả này để tuyên bố chất lượng generation thật.

## Worst performers

| # | Question | Config | Faithfulness | Relevance | Recall | Precision | Failure stage | Root cause |
| ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| 1 | Nếu nghi mình là nạn nhân phishing thì nên làm gì với các mật khẩu bị ảnh hưởng? | B | 1.000 | 0.000 | 0.000 | 0.000 | retrieval | Missed expected context ID(s): nist_phishing::chunk-11 |
| 2 | Vì sao verifier nên so sánh mật khẩu người dùng với blocklist? | B | 1.000 | 0.047 | 0.000 | 0.000 | retrieval | Missed expected context ID(s): nist-sp800-63b-4::chunk-549 |
| 3 | Vì sao OTP phải nhập thủ công không được xem là phishing-resistant? | B | 1.000 | 0.000 | 0.500 | 0.200 | retrieval | Missed expected context ID(s): nist-sp800-63b-4::chunk-244 |

## Recommendations

| Priority | Action | Evidence from failure analysis | Expected impact | How to verify |
| ---: | --- | --- | --- | --- |
| 1 | Tăng candidate hoặc rà lại chunk boundary cho các case mất expected_context. | Worst performers có context recall dưới 1 và liệt kê ID bị thiếu. | Tăng candidate chỉ ở bước retrieval và theo dõi recall; không đổi generator. | Chạy lại `python -m src.evaluate_ab` và kiểm tra context_recall từng case. |
| 2 | Giữ top_k cố định khi tinh chỉnh RRF; xem xét lọc nhiễu sau retrieval. | Một số case có expected evidence nhưng precision thấp do top-5 chứa nhiều chunk khác. | Tăng context precision và giảm context đưa vào generation, đổi lại có thể mất recall. | So sánh precision/recall theo từng case với cùng golden dataset. |
| 3 | Sau khi thêm LLM key, chạy cùng prompt qua generator thật và đánh giá lại relevance. | Evaluator hiện dùng extractive generator cố định; answer relevance thấp phản ánh wording khác reference. | Đo generation thật mà không thay retrieval, evaluator hoặc top_k giữa A/B. | Ghi model/version và chạy lại cả hai config trong một lần evaluation mới. |

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m src.evaluate_ab
.\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py -q
```

Detailed per-case rows and retrieval traces: [AB_RESULTS.json](../../reports/AB_RESULTS.json). Golden cases: [golden_dataset.json](golden_dataset.json). Production fallback calibration is documented in [THRESHOLD_CALIBRATION.json](../../reports/THRESHOLD_CALIBRATION.json).

## Bonus experiments

No bonus experiment is claimed. A real LLM generation run and a reranker comparison require separate controlled measurements with the same dataset and evaluator.
