"""查無門檻的挑法與 bootstrap 信賴區間。算法簡單，方便口頭解釋。"""
import numpy as np

BOOTSTRAP = 1000  # 重抽次數
SEED = 0          # 固定亂數種子：每次跑結果相同


def pick_threshold(answerable: list[float], unanswerable: list[float]) -> float:
    """每個「相鄰分數的中點」都試一次，算兩個比率相加：可回答題放行的比率（分數 >= 門檻）
    ＋ 不可回答題擋住的比率（分數 < 門檻）。選最高的；同分取最低的（少誤擋可回答題）。
    兩種題各算比率，因為 25 比 5 差很多，直接數題數會選到「什麼都不擋」。不強迫 5 題全擋住。"""
    pts = sorted(set(answerable) | set(unanswerable))
    if len(pts) < 2 or not answerable or not unanswerable:
        raise ValueError("需要兩種題、至少 2 種分數，才能挑門檻")
    na, nu = len(answerable), len(unanswerable)
    best, best_score = None, -1
    for lo, hi in zip(pts, pts[1:]):
        t = (lo + hi) / 2
        # 兩個比率相加，各乘 na*nu 換成整數比較，避免浮點數同分判錯
        score = sum(s >= t for s in answerable) * nu + sum(s < t for s in unanswerable) * na
        if score > best_score:
            best, best_score = t, score
    return best


def gate_outcome(answerable: dict, unanswerable: dict, threshold: float) -> dict:
    """題號 -> 最高分。最高分低於門檻（嚴格小於）就是查無。"""
    return {
        "answerable_blocked": [i for i, s in answerable.items() if s < threshold],
        "unanswerable_blocked": [i for i, s in unanswerable.items() if s < threshold],
        "unanswerable_passed": [i for i, s in unanswerable.items() if s >= threshold],
    }


def _rr(ranks):
    return np.array([1 / r if r else 0.0 for r in ranks])


def _means(rr_list, n, B, seed):
    """同一組重抽編號套到每一份倒數名次上，所以方式之間是配對的。"""
    idx = np.random.default_rng(seed).integers(0, n, size=(B, n))
    return [rr[idx].mean(axis=1) for rr in rr_list]


def _ci(x):
    lo, hi = np.percentile(x, [2.5, 97.5])
    return float(lo), float(hi)


def mrr_interval(ranks, B=BOOTSTRAP, seed=SEED) -> tuple[float, float]:
    """MRR 的 95% 區間：題目重抽 B 次（可重複），每次算 MRR，取 2.5% 與 97.5% 位置。"""
    return _ci(_means([_rr(ranks)], len(ranks), B, seed)[0])


def paired_diff_interval(ranks_a, ranks_b, B=BOOTSTRAP, seed=SEED) -> tuple[float, float]:
    """MRR(A) - MRR(B) 的 95% 區間。兩種方式用同一次重抽的題目。"""
    a, b = _means([_rr(ranks_a), _rr(ranks_b)], len(ranks_a), B, seed)
    return _ci(a - b)


def verdict(interval: tuple[float, float]) -> str:
    lo, hi = interval
    if lo > 0 or hi < 0:
        return "區間不含 0：差異可信（不是題目抽樣的運氣）"
    return "區間含 0：不能說兩者有差異（題少，可能只是運氣）"


def _vals(ranks, kind):
    """每題一個數：hit@1、hit@3 是 0 或 1，mrr 是倒數名次。"""
    if kind == "mrr":
        return _rr(ranks)
    k = int(kind.split("@")[1])
    return np.array([1.0 if r is not None and r <= k else 0.0 for r in ranks])


def metric_interval(ranks, kind, B=BOOTSTRAP, seed=SEED) -> tuple[float, float]:
    """hit@1、hit@3 或 mrr 的 95% 區間，做法同 mrr_interval。"""
    idx = np.random.default_rng(seed).integers(0, len(ranks), size=(B, len(ranks)))
    return _ci(_vals(ranks, kind)[idx].mean(axis=1))


def paired_metric_interval(ranks_a, ranks_b, kind, B=BOOTSTRAP, seed=SEED) -> tuple[float, float]:
    """指標(A) - 指標(B) 的 95% 區間，同一次重抽的題目。"""
    idx = np.random.default_rng(seed).integers(0, len(ranks_a), size=(B, len(ranks_a)))
    return _ci((_vals(ranks_a, kind)[idx] - _vals(ranks_b, kind)[idx]).mean(axis=1))
