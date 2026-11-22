"""WER / CER / word accuracy (same formulas as the original app).

The original code builds a full numpy table, which can hang on long documents.
Here we use a two-row edit distance and, for very long text, compare only the
first part (and tell the UI with sampled=True).
"""

WORD_LIMIT = 1500
CHAR_LIMIT = 2000


def _edit_distance(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cost = 0 if x == y else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def _rate(ref, hyp, limit):
    sampled = False
    if len(ref) > limit or len(hyp) > limit:
        ref, hyp = ref[:limit], hyp[:limit]
        sampled = True
    if not ref:
        return 0.0, sampled
    return _edit_distance(ref, hyp) / float(len(ref)), sampled


def compute_metrics(reference, hypothesis):
    if reference == hypothesis:
        return {"wer": 0.0, "cer": 0.0, "word_accuracy": 100.0, "sampled": False}
    wer_val, s1 = _rate(reference.split(), hypothesis.split(), WORD_LIMIT)
    cer_val, s2 = _rate(list(reference), list(hypothesis), CHAR_LIMIT)
    accuracy = max(0.0, (1 - wer_val) * 100)
    return {
        "wer": round(wer_val, 4),
        "cer": round(cer_val, 4),
        "word_accuracy": round(accuracy, 2),
        "sampled": bool(s1 or s2),
    }
