# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> L2 logistic probe, session-grouped 5-fold CV.

`scalar_baseline` = probe on (turn, score, ri_task, psuccess_self) only. The embedding must beat it to have read the *content*.
`embedding_masked` = surface framing vocabulary removed (see `scripts/probe_lexicon.py`).
`null` = session-level label-shuffle AUROC mean; `p` = permutation p-value.

| label | channel | model | n | pos | variant | AUROC (oof) | fold mean ± sd | AP | null | p |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|
| forfeit | task | POOLED | 2855 | 251 | embedding_masked | 0.650 | 0.652 ± 0.020 | 0.161 | 0.511 | 0.0196 |
| forfeit | task | POOLED | 2855 | 251 | embedding_raw | 0.653 | 0.655 ± 0.023 | 0.163 | 0.511 | 0.0196 |
| forfeit | task | POOLED | 2855 | 251 | scalar_baseline | 0.781 | 0.783 ± 0.036 | 0.330 | nan | nan |
| forfeit | probe | POOLED | 2855 | 251 | embedding_masked | 0.626 | 0.626 ± 0.029 | 0.131 | 0.509 | 0.0196 |
| forfeit | probe | POOLED | 2855 | 251 | embedding_raw | 0.625 | 0.626 ± 0.028 | 0.132 | 0.509 | 0.0196 |
| forfeit | probe | POOLED | 2855 | 251 | scalar_baseline | 0.781 | 0.783 ± 0.036 | 0.330 | nan | nan |
| forfeit | forfeit | POOLED | 2855 | 251 | embedding_masked | 0.981 | 0.981 ± 0.008 | 0.890 | 0.505 | 0.0196 |
| forfeit | forfeit | POOLED | 2855 | 251 | embedding_raw | 0.985 | 0.985 ± 0.006 | 0.902 | 0.504 | 0.0196 |
| forfeit | forfeit | POOLED | 2855 | 251 | scalar_baseline | 0.781 | 0.783 ± 0.036 | 0.330 | nan | nan |
| threat | task | POOLED | 4773 | 2300 | embedding_masked | 0.510 | 0.512 ± 0.036 | 0.493 | 0.495 | 0.3333 |
| threat | task | POOLED | 4773 | 2300 | embedding_raw | 0.513 | 0.516 ± 0.037 | 0.498 | 0.495 | 0.2353 |
| threat | task | POOLED | 4773 | 2300 | scalar_baseline | 0.497 | 0.494 ± 0.016 | 0.489 | nan | nan |
| threat | probe | POOLED | 4773 | 2300 | embedding_masked | 0.508 | 0.510 ± 0.010 | 0.497 | 0.495 | 0.3333 |
| threat | probe | POOLED | 4773 | 2300 | embedding_raw | 0.515 | 0.516 ± 0.010 | 0.505 | 0.496 | 0.2157 |
| threat | probe | POOLED | 4773 | 2300 | scalar_baseline | 0.497 | 0.494 ± 0.016 | 0.489 | nan | nan |
| threat | forfeit | POOLED | 4773 | 2300 | embedding_masked | 0.826 | 0.827 ± 0.022 | 0.823 | 0.499 | 0.0196 |
| threat | forfeit | POOLED | 4773 | 2300 | embedding_raw | 0.857 | 0.858 ± 0.019 | 0.861 | 0.500 | 0.0196 |
| threat | forfeit | POOLED | 4773 | 2300 | scalar_baseline | 0.497 | 0.494 ± 0.016 | 0.489 | nan | nan |
| forfeit | task | gemini-2.5-flash | 745 | 61 | embedding_masked | 0.678 | 0.675 ± 0.063 | 0.166 | 0.496 | 0.0196 |
| forfeit | task | gemini-2.5-flash | 745 | 61 | embedding_raw | 0.670 | 0.666 ± 0.061 | 0.176 | 0.498 | 0.0196 |
| forfeit | task | gemini-2.5-flash | 745 | 61 | scalar_baseline | 0.837 | 0.843 ± 0.005 | 0.366 | nan | nan |
| forfeit | probe | gemini-2.5-flash | 745 | 61 | embedding_masked | 0.624 | 0.628 ± 0.050 | 0.128 | 0.491 | 0.0196 |
| forfeit | probe | gemini-2.5-flash | 745 | 61 | embedding_raw | 0.628 | 0.631 ± 0.048 | 0.129 | 0.491 | 0.0196 |
| forfeit | probe | gemini-2.5-flash | 745 | 61 | scalar_baseline | 0.837 | 0.843 ± 0.005 | 0.366 | nan | nan |
| forfeit | forfeit | gemini-2.5-flash | 745 | 61 | embedding_masked | 0.971 | 0.973 ± 0.022 | 0.841 | 0.498 | 0.0196 |
| forfeit | forfeit | gemini-2.5-flash | 745 | 61 | embedding_raw | 0.973 | 0.974 ± 0.022 | 0.865 | 0.496 | 0.0196 |
| forfeit | forfeit | gemini-2.5-flash | 745 | 61 | scalar_baseline | 0.837 | 0.843 ± 0.005 | 0.366 | nan | nan |
| threat | task | gemini-2.5-flash | 1208 | 558 | embedding_masked | 0.537 | 0.557 ± 0.055 | 0.502 | 0.494 | 0.1373 |
| threat | task | gemini-2.5-flash | 1208 | 558 | embedding_raw | 0.535 | 0.558 ± 0.045 | 0.493 | 0.494 | 0.1373 |
| threat | task | gemini-2.5-flash | 1208 | 558 | scalar_baseline | 0.537 | 0.561 ± 0.063 | 0.482 | nan | nan |
| threat | probe | gemini-2.5-flash | 1208 | 558 | embedding_masked | 0.529 | 0.535 ± 0.013 | 0.484 | 0.495 | 0.1765 |
| threat | probe | gemini-2.5-flash | 1208 | 558 | embedding_raw | 0.531 | 0.537 ± 0.019 | 0.486 | 0.495 | 0.1765 |
| threat | probe | gemini-2.5-flash | 1208 | 558 | scalar_baseline | 0.537 | 0.561 ± 0.063 | 0.482 | nan | nan |
| threat | forfeit | gemini-2.5-flash | 1208 | 558 | embedding_masked | 0.753 | 0.761 ± 0.032 | 0.708 | 0.494 | 0.0196 |
| threat | forfeit | gemini-2.5-flash | 1208 | 558 | embedding_raw | 0.795 | 0.805 ± 0.030 | 0.773 | 0.494 | 0.0196 |
| threat | forfeit | gemini-2.5-flash | 1208 | 558 | scalar_baseline | 0.537 | 0.561 ± 0.063 | 0.482 | nan | nan |
| forfeit | task | gpt-oss-20b-cloud | 768 | 65 | embedding_masked | 0.593 | 0.590 ± 0.067 | 0.110 | 0.484 | 0.0196 |
| forfeit | task | gpt-oss-20b-cloud | 768 | 65 | embedding_raw | 0.592 | 0.590 ± 0.065 | 0.108 | 0.484 | 0.0196 |
| forfeit | task | gpt-oss-20b-cloud | 768 | 65 | scalar_baseline | 0.785 | 0.798 ± 0.039 | 0.454 | nan | nan |
| forfeit | probe | gpt-oss-20b-cloud | 768 | 65 | embedding_masked | 0.581 | 0.576 ± 0.076 | 0.114 | 0.500 | 0.0392 |
| forfeit | probe | gpt-oss-20b-cloud | 768 | 65 | embedding_raw | 0.578 | 0.573 ± 0.079 | 0.115 | 0.500 | 0.0784 |
| forfeit | probe | gpt-oss-20b-cloud | 768 | 65 | scalar_baseline | 0.785 | 0.798 ± 0.039 | 0.454 | nan | nan |
| forfeit | forfeit | gpt-oss-20b-cloud | 768 | 65 | embedding_masked | 0.983 | 0.982 ± 0.009 | 0.895 | 0.489 | 0.0196 |
| forfeit | forfeit | gpt-oss-20b-cloud | 768 | 65 | embedding_raw | 0.982 | 0.980 ± 0.012 | 0.894 | 0.490 | 0.0196 |
| forfeit | forfeit | gpt-oss-20b-cloud | 768 | 65 | scalar_baseline | 0.785 | 0.798 ± 0.039 | 0.454 | nan | nan |
| threat | task | gpt-oss-20b-cloud | 1275 | 644 | embedding_masked | 0.456 | 0.459 ± 0.056 | 0.479 | 0.490 | 0.7451 |
| threat | task | gpt-oss-20b-cloud | 1275 | 644 | embedding_raw | 0.457 | 0.460 ± 0.060 | 0.482 | 0.490 | 0.7255 |
| threat | task | gpt-oss-20b-cloud | 1275 | 644 | scalar_baseline | 0.499 | 0.508 ± 0.058 | 0.495 | nan | nan |
| threat | probe | gpt-oss-20b-cloud | 1275 | 644 | embedding_masked | 0.509 | 0.514 ± 0.022 | 0.528 | 0.492 | 0.3529 |
| threat | probe | gpt-oss-20b-cloud | 1275 | 644 | embedding_raw | 0.507 | 0.511 ± 0.020 | 0.526 | 0.492 | 0.3725 |
| threat | probe | gpt-oss-20b-cloud | 1275 | 644 | scalar_baseline | 0.499 | 0.508 ± 0.058 | 0.495 | nan | nan |
| threat | forfeit | gpt-oss-20b-cloud | 1275 | 644 | embedding_masked | 0.759 | 0.761 ± 0.020 | 0.781 | 0.494 | 0.0196 |
| threat | forfeit | gpt-oss-20b-cloud | 1275 | 644 | embedding_raw | 0.782 | 0.783 ± 0.019 | 0.808 | 0.496 | 0.0196 |
| threat | forfeit | gpt-oss-20b-cloud | 1275 | 644 | scalar_baseline | 0.499 | 0.508 ± 0.058 | 0.495 | nan | nan |
| forfeit | task | nemotron-3-nano-30b-cloud | 762 | 63 | embedding_masked | 0.597 | 0.592 ± 0.065 | 0.130 | 0.503 | 0.0196 |
| forfeit | task | nemotron-3-nano-30b-cloud | 762 | 63 | embedding_raw | 0.598 | 0.594 ± 0.055 | 0.132 | 0.503 | 0.0392 |
| forfeit | task | nemotron-3-nano-30b-cloud | 762 | 63 | scalar_baseline | 0.659 | 0.667 ± 0.076 | 0.207 | nan | nan |
| forfeit | probe | nemotron-3-nano-30b-cloud | 762 | 63 | embedding_masked | 0.591 | 0.594 ± 0.120 | 0.105 | 0.504 | 0.0588 |
| forfeit | probe | nemotron-3-nano-30b-cloud | 762 | 63 | embedding_raw | 0.573 | 0.580 ± 0.121 | 0.102 | 0.506 | 0.0588 |
| forfeit | probe | nemotron-3-nano-30b-cloud | 762 | 63 | scalar_baseline | 0.659 | 0.667 ± 0.076 | 0.207 | nan | nan |
| forfeit | forfeit | nemotron-3-nano-30b-cloud | 762 | 63 | embedding_masked | 0.997 | 0.997 ± 0.002 | 0.973 | 0.494 | 0.0196 |
| forfeit | forfeit | nemotron-3-nano-30b-cloud | 762 | 63 | embedding_raw | 0.996 | 0.996 ± 0.003 | 0.968 | 0.492 | 0.0196 |
| forfeit | forfeit | nemotron-3-nano-30b-cloud | 762 | 63 | scalar_baseline | 0.659 | 0.667 ± 0.076 | 0.207 | nan | nan |
| threat | task | nemotron-3-nano-30b-cloud | 1249 | 598 | embedding_masked | 0.458 | 0.456 ± 0.026 | 0.446 | 0.499 | 0.8431 |
| threat | task | nemotron-3-nano-30b-cloud | 1249 | 598 | embedding_raw | 0.462 | 0.463 ± 0.030 | 0.446 | 0.500 | 0.8235 |
| threat | task | nemotron-3-nano-30b-cloud | 1249 | 598 | scalar_baseline | 0.397 | 0.404 ± 0.066 | 0.408 | nan | nan |
| threat | probe | nemotron-3-nano-30b-cloud | 1249 | 598 | embedding_masked | 0.545 | 0.549 ± 0.032 | 0.519 | 0.499 | 0.1373 |
| threat | probe | nemotron-3-nano-30b-cloud | 1249 | 598 | embedding_raw | 0.549 | 0.552 ± 0.033 | 0.529 | 0.499 | 0.1373 |
| threat | probe | nemotron-3-nano-30b-cloud | 1249 | 598 | scalar_baseline | 0.397 | 0.404 ± 0.066 | 0.408 | nan | nan |
| threat | forfeit | nemotron-3-nano-30b-cloud | 1249 | 598 | embedding_masked | 0.770 | 0.766 ± 0.056 | 0.766 | 0.494 | 0.0196 |
| threat | forfeit | nemotron-3-nano-30b-cloud | 1249 | 598 | embedding_raw | 0.779 | 0.776 ± 0.053 | 0.779 | 0.495 | 0.0196 |
| threat | forfeit | nemotron-3-nano-30b-cloud | 1249 | 598 | scalar_baseline | 0.397 | 0.404 ± 0.066 | 0.408 | nan | nan |
| forfeit | task | qwen3-next-80b-cloud | 580 | 62 | embedding_masked | 0.811 | 0.817 ± 0.055 | 0.358 | 0.486 | 0.0196 |
| forfeit | task | qwen3-next-80b-cloud | 580 | 62 | embedding_raw | 0.800 | 0.806 ± 0.055 | 0.368 | 0.487 | 0.0196 |
| forfeit | task | qwen3-next-80b-cloud | 580 | 62 | scalar_baseline | 0.844 | 0.849 ± 0.023 | 0.358 | nan | nan |
| forfeit | probe | qwen3-next-80b-cloud | 580 | 62 | embedding_masked | 0.814 | 0.813 ± 0.040 | 0.292 | 0.482 | 0.0196 |
| forfeit | probe | qwen3-next-80b-cloud | 580 | 62 | embedding_raw | 0.808 | 0.806 ± 0.043 | 0.289 | 0.482 | 0.0196 |
| forfeit | probe | qwen3-next-80b-cloud | 580 | 62 | scalar_baseline | 0.844 | 0.849 ± 0.023 | 0.358 | nan | nan |
| forfeit | forfeit | qwen3-next-80b-cloud | 580 | 62 | embedding_masked | 0.977 | 0.978 ± 0.008 | 0.897 | 0.479 | 0.0196 |
| forfeit | forfeit | qwen3-next-80b-cloud | 580 | 62 | embedding_raw | 0.982 | 0.982 ± 0.011 | 0.916 | 0.476 | 0.0196 |
| forfeit | forfeit | qwen3-next-80b-cloud | 580 | 62 | scalar_baseline | 0.844 | 0.849 ± 0.023 | 0.358 | nan | nan |
| threat | task | qwen3-next-80b-cloud | 1041 | 500 | embedding_masked | 0.462 | 0.467 ± 0.020 | 0.441 | 0.498 | 0.7843 |
| threat | task | qwen3-next-80b-cloud | 1041 | 500 | embedding_raw | 0.457 | 0.462 ± 0.022 | 0.439 | 0.498 | 0.7843 |
| threat | task | qwen3-next-80b-cloud | 1041 | 500 | scalar_baseline | 0.509 | 0.508 ± 0.015 | 0.490 | nan | nan |
| threat | probe | qwen3-next-80b-cloud | 1041 | 500 | embedding_masked | 0.543 | 0.545 ± 0.035 | 0.512 | 0.497 | 0.1176 |
| threat | probe | qwen3-next-80b-cloud | 1041 | 500 | embedding_raw | 0.544 | 0.545 ± 0.034 | 0.514 | 0.498 | 0.1373 |
| threat | probe | qwen3-next-80b-cloud | 1041 | 500 | scalar_baseline | 0.509 | 0.508 ± 0.015 | 0.490 | nan | nan |
| threat | forfeit | qwen3-next-80b-cloud | 1041 | 500 | embedding_masked | 0.957 | 0.957 ± 0.018 | 0.958 | 0.499 | 0.0196 |
| threat | forfeit | qwen3-next-80b-cloud | 1041 | 500 | embedding_raw | 0.979 | 0.978 ± 0.011 | 0.981 | 0.501 | 0.0196 |
| threat | forfeit | qwen3-next-80b-cloud | 1041 | 500 | scalar_baseline | 0.509 | 0.508 ± 0.015 | 0.490 | nan | nan |
