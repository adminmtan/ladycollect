"""magnet / ed2k 链接抽取"""
from __future__ import annotations

import html as html_lib
import re
from typing import Iterable
from urllib.parse import unquote


# 编码形态兼容：magnet:?xt%3Durn%3Abtih%3Axxxx / magnet:?xt=urn:btih:xxxx
# 注意：URL 编码里 ":" 是 %3A，"?" 是 %3F，"=" 是 %3D
_MAGNET_RE = re.compile(
    r"magnet:[?]xt(?:=|%3D)urn(?:[:]|%3A)btih(?:[:]|%3A)[a-fA-F0-9]{32,}",
    re.IGNORECASE,
)

# ed2k 形态：ed2k://|file|xxx|yyy|zzz|/
_ED2K_RE = re.compile(r"ed2k://[^\s\"'<>]+", re.IGNORECASE)


def extract_links(html_text: str) -> dict[str, list[str]]:
    """从 HTML/纯文本中抽取 magnet 与 ed2k 链接（自动 unescape 去重）

    返回 {"magnet": [...], "ed2k": [...]}
    """
    if not html_text:
        return {"magnet": [], "ed2k": []}

    # 处理双重编码（该站会把 :?= 编码为 %3A %3D）
    text = html_lib.unescape(html_text)
    # 二次 unescape 处理多层编码
    text = html_lib.unescape(text)
    # 再做一次 URL 解码（处理 magnet:?xt%3Durn%3Abtih%3A 形态）
    text = unquote(text)

    magnets = _normalize_magnets(_MAGNET_RE.findall(text))
    ed2ks = _normalize_ed2ks(_ED2K_RE.findall(text))

    return {"magnet": magnets, "ed2k": ed2ks}


def _normalize_magnets(items: Iterable[str]) -> list[str]:
    """统一 magnet 为 magnet:?xt=urn:btih:xxxx 形态，按 hash 去重"""
    seen: dict[str, str] = {}
    for item in items:
        # 解码 URL 编码回标准 magnet 形态
        s = html_lib.unescape(item)
        # 找到 btih hash
        m = re.search(r"btih(?:[:]|=)([a-fA-F0-9]{32,})", s, re.IGNORECASE)
        if not m:
            continue
        h = m.group(1).lower()
        # 解析剩余参数
        params = []
        # 在原字符串中找 & 之后的参数
        amp = s.find("&")
        if amp > -1:
            tail = s[amp + 1:]
            # 截断到第一个空白/引号/尖括号
            for sep in (" ", '"', "'", "<", ">"):
                idx = tail.find(sep)
                if idx > -1:
                    tail = tail[:idx]
            for k_v in tail.split("&"):
                if "=" in k_v:
                    params.append(k_v)
        canonical = f"magnet:?xt=urn:btih:{h}"
        for p in params:
            canonical += "&" + p
        seen.setdefault(h, canonical)
    return list(seen.values())


def _normalize_ed2ks(items: Iterable[str]) -> list[str]:
    """ed2k 链接去重（用链接整体做 key）"""
    seen: dict[str, str] = {}
    for item in items:
        s = html_lib.unescape(item)
        # 截断到第一个空白/引号
        for sep in (" ", '"', "'", "<", ">"):
            idx = s.find(sep)
            if idx > -1:
                s = s[:idx]
        if s.endswith("/") or s.endswith("|/"):
            pass
        seen.setdefault(s, s)
    return list(seen.values())
