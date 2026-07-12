from __future__ import annotations

import re
from dataclasses import dataclass


FIXED_TAXONOMY = {
    "food_delivery": "餐饮外卖",
    "groceries": "超市便利",
    "lottery": "彩票",
    "personal_transfer": "个人转账",
    "uncategorized": "未分类",
}
CATEGORY_TAXONOMY = FIXED_TAXONOMY


@dataclass(frozen=True)
class LocalClassificationResult:
    category: str
    thing: str | None
    confidence: float
    reason: str


LOCAL_CATEGORY_RULES = (
    ("personal_transfer", ("向个人", "个人收款", "转账给", "二维码收款", "个人转账")),
    ("lottery", ("体彩", "福彩", "福利彩票", "彩票")),
    ("groceries", ("便利店", "超市", "新佳宜", "乐尔乐", "罗森", "全家", "美宜佳", "芙蓉兴盛")),
    ("food_delivery", ("美团", "饿了么", "外卖", "餐饮", "麦当劳", "肯德基")),
)


def normalize_matching_text(*values: str | None) -> str:
    return re.sub(r"\s+", "", "".join(value or "" for value in values)).lower()


def classify_locally(
    *,
    merchant: str | None,
    product: str | None,
    platform: str | None,
    payment_app: str | None,
    text: str,
) -> LocalClassificationResult:
    haystack = normalize_matching_text(merchant, product, platform, payment_app, text)
    for category, hints in LOCAL_CATEGORY_RULES:
        if any(hint in haystack for hint in hints):
            return LocalClassificationResult(
                category=category,
                thing=FIXED_TAXONOMY[category],
                confidence=0.95,
                reason=f"local_rule:{category}",
            )
    return LocalClassificationResult(
        category="uncategorized",
        thing=None,
        confidence=0.0,
        reason="local_rule:none",
    )


def detect_category_and_thing(text: str, product: str | None) -> tuple[str, str | None]:
    result = classify_locally(
        merchant=None,
        product=product,
        platform=None,
        payment_app=None,
        text=text,
    )
    return result.category, result.thing
