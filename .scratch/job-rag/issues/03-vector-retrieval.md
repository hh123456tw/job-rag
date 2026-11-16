# 03: 向量檢索與混合，共 5 種方式

**Blocked by:** 02
**Status:** ready-for-agent

**What to build:** 在同一個縫上加入 bge-small-zh、bge-m3、multilingual-e5（FAISS）與混合（BM25＋bge-m3，RRF，k=60）。評估表擴成 5 種。

- [ ] 下載任何模型前，先回報實際大小並等使用者同意（需要使用者）
- [ ] 檢索全在本機執行
- [ ] 5 種方式在同 30 題上都有 Hit@1、Hit@3、MRR
- [ ] 若命中率接近 100%，在結果中標示「先懷疑題目太簡單」
