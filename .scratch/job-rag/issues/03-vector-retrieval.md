# 03: 向量檢索與混合，共 5 種方式

**Blocked by:** 02
**Status:** resolved

**What to build:** 在同一個縫上加入 bge-small-zh、bge-m3、multilingual-e5（FAISS）與混合（BM25＋bge-m3，RRF，k=60）。評估表擴成 5 種。

- [x] 下載任何模型前，先回報實際大小並等使用者同意（需要使用者）
- [x] 檢索全在本機執行
- [x] 5 種方式在同 30 題上都有 Hit@1、Hit@3、MRR
- [x] 若命中率接近 100%，在結果中標示「先懷疑題目太簡單」

## Comments

- 程式與測試完成；成績見 eval/results_methods.txt。待使用者確認（題目仍待票 02 確認）。

## Comments

- 完成。實際下載 4,641,211,567 位元組（約 4.32 GiB）。5 種方式成績表在 eval/results_methods.txt。bge-m3 MRR 0.960，混合 0.873；題少，只能當方向。題組仍會被票 10 的題目修訂改動，之後要重跑。
