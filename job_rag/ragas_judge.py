"""RAGAS 評審：用 DeepSeek（OpenAI 相容端點）當評審 LLM，本機 bge-m3 當嵌入模型。
需要 ragas==0.4.4（見 requirements-ragas.txt）。只有 make_scorer() 才 import ragas。
官方文件：https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
          https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/"""
import asyncio
import os

from .answer import DEFAULT_MODEL, _key

BASE_URL = "https://api.deepseek.com"  # https://api-docs.deepseek.com/ ；OpenAI SDK 的 base_url


def _embed_fn(texts):
    from . import retrieval
    return retrieval._encode("bge-m3", texts, is_query=True).tolist()  # 本機 bge-m3，已正規化


def make_scorer(env_file=".env", base_url=BASE_URL, embed_fn=_embed_fn):
    """回傳 score_fn(question, answer, contexts) -> {"faithfulness", "answer_relevancy"}；失敗丟例外。"""
    import instructor
    from openai import AsyncOpenAI
    from ragas.embeddings.base import BaseRagasEmbedding
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, Faithfulness

    class LocalEmbedding(BaseRagasEmbedding):
        def embed_text(self, text, **kw):
            return embed_fn([text])[0]

        async def aembed_text(self, text, **kw):
            return await asyncio.to_thread(self.embed_text, text)

        def embed_texts(self, texts, **kw):
            return embed_fn(list(texts))

        async def aembed_texts(self, texts, **kw):
            return await asyncio.to_thread(self.embed_texts, texts)

    key = _key(env_file)
    model = os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
    emb = LocalEmbedding()

    async def _score(question, text, contexts):
        # 客戶端在事件圈內建立：每題一個 asyncio.run，避免連線池跨圈
        client = AsyncOpenAI(api_key=key, base_url=base_url, timeout=60, max_retries=0)
        try:
            # DeepSeek 只支援 json_object，不支援 json_schema：用 instructor.Mode.JSON
            llm = llm_factory(model, client=client, mode=instructor.Mode.JSON,
                              extra_body={"thinking": {"type": "disabled"}}, max_tokens=4096)
            f = await Faithfulness(llm=llm).ascore(user_input=question, response=text, retrieved_contexts=contexts)
            a = await AnswerRelevancy(llm=llm, embeddings=emb).ascore(user_input=question, response=text)
        finally:
            await client.close()
        return {"faithfulness": f.value, "answer_relevancy": a.value}

    return lambda question, text, contexts: asyncio.run(_score(question, text, contexts))
