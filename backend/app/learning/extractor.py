"""智能过滤学习 - 关键词提取器

从用户标记「不喜欢」/「喜欢」的帖子标题中，提取可复用的过滤关键词。

策略：
1. 优先调用 OpenAI 兼容 API（gpt-4o-mini 等），用 prompt 让模型返回结构化关键词
2. 当 API 不可用（未配置 key、网络超时、解析失败）时，降级到本地规则提取：
   - 中文 2-4 字子串频率统计
   - 英文单词
   - 数字/版本号
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Iterable

from app.config import settings

logger = logging.getLogger(__name__)


# 过滤掉的高频通用词（不应作为过滤关键词）
_LOCAL_STOPWORDS = {
    # 中文高频通用词
    "高清", "无码", "有码", "步兵", "骑兵", "原创", "首发", "合集", "全集", "系列",
    "字幕", "字幕版", "中文", "日语", "日语中字", "中字", "完整版", "完整", "高清版",
    "未删减", "未删", "删减", "抢先", "网盘", "磁力", "下载", "种子", "资源",
    "在线", "播放", "观看", "视频", "免费", "最新", "今日", "本周", "本月",
    # 英文/数字
    "hd", "4k", "1080p", "720p", "bluray", "dvd", "dvdrip", "web", "webrip",
    # 量词/单字
    "个", "部", "集", "第", "集", "话", "话", "番",
}

# 中文常用字（CJK 范围），用于本地子串统计
_CJK_RANGE = re.compile(r"[\u4e00-\u9fff]")


def _clean_keyword(kw: str) -> str:
    """规范化关键词：去空 → lowercase → 去前后空格/标点"""
    if not kw:
        return ""
    k = kw.strip().lower()
    # 去掉前后常见标点
    k = re.sub(r"^[\s,，.。:：;；、/\-_()()【】\[\]「」『』]+", "", k)
    k = re.sub(r"[\s,，.。:：;；、/\-_()()【】\[\]「」『』]+$", "", k)
    return k


def _extract_structured_tokens(title: str) -> list[str]:
    """从单标题里提取结构化 token:
    - [xxx] 方括号标签 (题材/分区, 如 [国产无码])
    - 【xxx】 书名号 (人物/系列, 如 【杀手蛇蛇】)
    返回时去掉方括号本身.
    过滤掉纯数字+容量标签 (如 14V/8.9G, 1080P, 714P/355M, 21V 等).
    """
    out: list[str] = []
    _JUNK_RE = re.compile(r"^[\d\.\-/vVmMgGbBpP]+$")
    for m in re.finditer(r"\[([^\]]{2,30})\]", title):
        v = m.group(1).strip()
        if not v:
            continue
        if _JUNK_RE.match(v):  # 纯数字 / 容量规格
            continue
        if v not in out:
            out.append(v)
    for m in re.finditer(r"【([^】]{2,30})】", title):
        v = m.group(1).strip()
        # 过滤掉 "最新/高清/完结/中字" 这种通用词
        if v and v not in out and not any(sw in v for sw in ("最新", "无水印", "高清", "完结", "中字", "无码")):
            out.append(v)
    return out


def _filter_overlapping_ngrams(tokens: list[str]) -> list[str]:
    """去掉中文 n-gram 切碎的错位重叠子串.
    例: ['国产无码','产无码萝','无码萝御'] -> 只保留最长的 '国产无码'.

    规则: 对每个 token k, 若存在另一个更长 token long (|long|>|k|),
    k 的字符集 ⊆ long 的字符集 且 k 的字符数 ≥ long 一半, 则视为重叠冗余.
    """
    out: list[str] = []
    for k in tokens:
        k_chars = set(k)
        is_overlap = False
        for existing in out:
            if len(existing) <= len(k):
                continue
            e_chars = set(existing)
            if k_chars <= e_chars and len(k) >= len(existing) / 2:
                is_overlap = True
                break
        if not is_overlap:
            out.append(k)
    return out


class LocalKeywordExtractor:
    """本地规则关键词提取器（无外部依赖）

    策略：
    - 中文：n-gram (2-4 字) 频率，过滤掉停用词
    - 英文：单词
    - 数字 + 单位（GB/MB/期/集）
    """

    @staticmethod
    def extract(titles: Iterable[str], top_n: int = 8) -> list[str]:
        titles = [t for t in titles if t]
        if not titles:
            return []

        # n-gram 出现次数（含跨标题合并去重，按 score 排）
        gram_scores: Counter[str] = Counter()
        # 同时统计每个 gram 出现在多少不同标题里（区分度）
        gram_doc_freq: dict[str, int] = {}

        for title in titles:
            seen_in_title: set[str] = set()
            t = title.lower()

            # 1) 中文 n-gram
            cjk_chars = "".join(_CJK_RANGE.findall(title))
            for n in (2, 3, 4):
                for i in range(0, max(1, len(cjk_chars) - n + 1)):
                    gram = cjk_chars[i : i + n]
                    if not gram or gram in _LOCAL_STOPWORDS:
                        continue
                    # 任何字符在停用词中的，整体跳过
                    if any(c in _LOCAL_STOPWORDS for c in gram):
                        continue
                    # 越长的越有价值
                    weight = 2 if n == 2 else (3 if n == 3 else 4)
                    gram_scores[gram] += weight
                    if gram not in seen_in_title:
                        gram_doc_freq[gram] = gram_doc_freq.get(gram, 0) + 1
                        seen_in_title.add(gram)

            # 2) 英文单词
            for word in re.findall(r"[a-z][a-z0-9]{2,}", t):
                if word in _LOCAL_STOPWORDS:
                    continue
                gram_scores[word] += 2
                if word not in seen_in_title:
                    gram_doc_freq[word] = gram_doc_freq.get(word, 0) + 1
                    seen_in_title.add(word)

            # 3) 数字 + 单位：例如 1080p、04期、Vol.12
            for m in re.finditer(r"\d+[a-z]{1,4}", t):
                tok = m.group(0)
                gram_scores[tok] += 3
                if tok not in seen_in_title:
                    gram_doc_freq[tok] = gram_doc_freq.get(tok, 0) + 1
                    seen_in_title.add(tok)
            for m in re.finditer(r"vol\.?\s*\d+", t, flags=re.I):
                tok = m.group(0).lower().replace(" ", "")
                gram_scores[tok] += 3
                if tok not in seen_in_title:
                    gram_doc_freq[tok] = gram_doc_freq.get(tok, 0) + 1
                    seen_in_title.add(tok)

        n_titles = max(1, len(titles))

        # 综合评分：frequency * doc_freq_ratio（区分度）
        ranked: list[tuple[float, str]] = []
        for gram, freq in gram_scores.items():
            df = gram_doc_freq.get(gram, 0) / n_titles
            # df 至少 0.4 才有区分度；超过 1.0 时是出现在所有标题中的核心词
            if df < 0.4:
                continue
            score = freq * (0.5 + df)
            ranked.append((score, gram))

        ranked.sort(key=lambda x: -x[0])

        # 取 top，剔除被更长 token 完全包含的低区分度短词
        out: list[str] = []
        seen: set[str] = set()
        for _, gram in ranked:
            g = _clean_keyword(gram)
            if not g or len(g) < 2 or g in seen:
                continue
            if g in _LOCAL_STOPWORDS:
                continue
            # 如果已收录更长且覆盖当前，跳过（避免「某演」「某演员」并存）
            if any(g in longer for longer in seen):
                continue
            seen.add(g)
            out.append(g)
            if len(out) >= top_n:
                break

        # ★ 单标题场景: n-gram 切碎会输出大量重叠子串 (例如 「国产无码」「产无码萝」「无码萝御」...),
        # 用户看到「AI 没分析」。补救: 只输出结构化 token ([xxx] 【xxx】), 跳过 n-gram.
        if len(titles) == 1 and titles[0]:
            title = titles[0]
            extracted = _extract_structured_tokens(title)
            return extracted[:top_n]

        return out


class AIKeywordExtractor:
    """OpenAI 兼容 API 关键词提取器

    通过 OPENAI_BASE_URL + OPENAI_API_KEY + OPENAI_MODEL 调用。
    """

    SYSTEM_PROMPT = """你是一名「中文视频网站过滤关键词提取助手」。
系统会用「标题是否包含该关键词」的子串匹配来过滤帖子。
你必须遵守：

【格式】
- 严格每行一个关键词
- 不要编号、不要解释、不要其他文字
- 不要 Markdown 代码块

【长度】
- 关键词最少 2 个字符（单字无意义，会被滤掉）
- 建议 3-12 个字符

【优先级：先输出最有区分度的】
1. 题材/分区标签（如「国产无码」「日本有码」「AI国语短剧」「ASMR」）
2. 系列名/作品名（如「美丽新世界」「杀手蛇蛇」）
3. 演员/作者/品牌名（如「yoonying」「池甜」）
4. 风格/特征词（如「擦边」「合集」）

【必须避免】
- 单字（"国"、"剧"、"人"等）
- 通用品质词（「高清」「无水印」「完结」「中字」「1080p」「720p」）
- 纯数字 / 集数 / 容量规格（如「14V」「8.9G」「1-14集」「714P」）
- 标点片段（如「-」「/」「[」）
- 量词（「第一集」「第二弹」）
- 时间词（「2025」「2026」「10月」）
"""

    EXTRACT_PROMPT = """用户刚刚把以下帖子标记为「{action_label}」。

请提取出 {top_n} 个能用作过滤关键词的字符串，能把这一类帖子都识别出来。

要求：
- 关键词是「子串匹配」，标题里出现该关键词就算命中
- 优先输出完整标签（如「国产无码」整体，不要拆成「国产」+「无码」）
- 完整标签命中更精准，避免输出过短导致误伤

{action_label}的标题列表：
{titles_block}
"""

    def __init__(self) -> None:
        # 优先级：app_settings 表 > env > 字段默认
        from app.services.settings import get_setting

        self.base_url = get_setting("openai_base_url")[0] or "https://api.openai.com/v1"
        self.api_key = get_setting("openai_api_key")[0]
        self.model = get_setting("openai_model")[0] or "gpt-4o-mini"
        try:
            self.timeout = int(get_setting("openai_timeout")[0] or "20")
        except (TypeError, ValueError):
            self.timeout = 20

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def extract(self, titles: list[str], action: str = "dislike", top_n: int = 8) -> list[str]:
        """同步调用 OpenAI chat/completions

        失败返回空列表（调用方应降级到本地提取器）
        """
        if not self.enabled:
            return []
        if not titles:
            return []

        action_label = {"dislike": "不喜欢", "like": "喜欢"}.get(action, "不喜欢")
        titles_block = "\n".join(f"- {t}" for t in titles[:30])
        prompt = self.EXTRACT_PROMPT.format(
            action_label=action_label,
            top_n=top_n,
            titles_block=titles_block,
        )

        try:
            # 用 stdlib urllib 直接打，兼容所有 OpenAI 兼容服务（无需第三方包）
            import json as _json
            import ssl
            import urllib.error
            import urllib.request

            ssl_ctx = ssl.create_default_context()
            try:
                import certifi
                ssl_ctx.load_verify_locations(certifi.where())
            except Exception:
                pass
            try:
                ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            except AttributeError:
                pass

            req_body = _json.dumps({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 200,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url.rstrip('/')}/chat/completions",
                data=req_body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout, context=ssl_ctx) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = _json.loads(raw) if raw else {}
            choices = data.get("choices") or []
            if not choices:
                return []
            content = choices[0].get("message", {}).get("content", "")
            return self._parse_keywords(content)
        except urllib.error.HTTPError as e:
            try:
                snippet = (e.read().decode("utf-8", errors="replace") or "")[:200]
            except Exception:
                snippet = ""
            logger.warning("AI 提取器 HTTP %s：%s", e.code, snippet)
            return []
        except (urllib.error.URLError, _json.JSONDecodeError, KeyError) as e:
            logger.warning("AI 提取器异常：%s", e)
            return []

    @staticmethod
    def _parse_keywords(text: str) -> list[str]:
        """解析模型输出：每行一个；过滤掉空行/编号/解释"""
        out: list[str] = []
        for line in text.splitlines():
            k = line.strip()
            if not k:
                continue
            # 去掉前导编号：「1. xxx」「- xxx」「* xxx」「① xxx」
            k = re.sub(r"^[\-\*\.\d\)\(①-⑩]+\s*", "", k)
            k = _clean_keyword(k)
            if k and len(k) >= 2 and k not in out:
                out.append(k)
        return out


class KeywordExtractor:
    """统一入口：AI 优先，本地降级"""

    def __init__(self) -> None:
        self.ai = AIKeywordExtractor()
        self.local = LocalKeywordExtractor()

    def extract(self, titles: list[str], action: str = "dislike", top_n: int = 8) -> tuple[list[str], str]:
        """返回 (关键词列表, 提取方式 'ai' | 'local')"""
        if self.ai.enabled:
            kws = self.ai.extract(titles, action=action, top_n=top_n)
            if kws:
                return kws, "ai"
        # 降级
        kws = self.local.extract(titles, top_n=top_n)
        return kws, "local"


# 全局单例
_extractor: KeywordExtractor | None = None


def get_extractor() -> KeywordExtractor:
    global _extractor
    if _extractor is None:
        _extractor = KeywordExtractor()
    return _extractor
