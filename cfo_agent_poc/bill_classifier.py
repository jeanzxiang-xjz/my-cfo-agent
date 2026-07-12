from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


FIXED_TAXONOMY = {
    "education": "证券考试",
    "books": "图书",
    "property": "物业服务",
    "telecom": "通信充值",
    "entertainment": "演出票务",
    "credit_repayment": "信用借还",
    "utilities": "水电燃缴费",
    "parking": "停车缴费",
    "car_charging": "车辆充电",
    "auto": "爱车养车",
    "groceries": "超市便利",
    "fruit": "水果",
    "bakery": "烘焙",
    "coffee_tea": "咖啡茶饮",
    "food_delivery": "餐饮外卖",
    "transport": "交通出行",
    "stationery": "文具用品",
    "ecommerce": "网购",
    "investment": "理财",
    "healthcare": "医疗",
    "digital_services": "数字服务",
    "general_shopping": "日常购物",
    "leisure_travel": "休闲旅行",
    "lottery": "彩票",
    "personal_transfer": "个人转账",
    "uncategorized": "未分类",
}
CATEGORY_TAXONOMY = FIXED_TAXONOMY


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    thing: str | None
    confidence: float
    source: str
    status: str
    reason: str | None


LocalClassificationResult = ClassificationResult


# Preserve the original category rules and add only the new local categories.
LOCAL_CATEGORY_RULES = (
    ("education", "证券考试", ("证券行业专业人员水平评价", "考试", "报名", "中国证券业协会")),
    ("books", "图书", ("新华书店", "湖南省新华书店", "书店", "图书", "教材", "书籍")),
    ("property", "物业服务", ("物业", "碧桂园生活服务", "生活服务集团", "物业费", "物业服务")),
    ("telecom", "通信充值", ("手机充值", "手机话费", "话费", "中国电信", "中国移动", "中国联通", "全渠道运营中心")),
    ("entertainment", "演出票务", ("大麦", "大麦网", "演出", "赛事票品", "票品", "电影票", "演唱会")),
    ("credit_repayment", "信用借还", ("花呗自动还款", "还款到", "信用借还", "账单还款", "还款成功")),
    ("utilities", "水电燃缴费", ("缴费说明", "电费", "水费", "燃气费", "燃气繳费", "新奥燃气", "供电分公司", "长沙供电", "户号")),
    ("parking", "停车缴费", ("停车缴费", "停车费", "停车", "在停订单", "顺易通", "静态交通", "jspay")),
    ("car_charging", "车辆充电", ("充电桩充值", "充电桩", "华自充电", "特来电", "星星充电", "小桔充电", "新电途")),
    ("auto", "爱车养车", ("爱车养车", "特斯拉", "TESLA", "Tesla", "加油", "洗车", "汽车保养", "车险")),
    ("groceries", "超市便利", ("超市", "便利店", "小卖部", "食品店", "泡菜店", "购物超市", "连锁便利店", "便利店-消费", "新佳宜", "乐尔乐", "罗森", "全家", "美宜佳", "芙蓉兴盛", "十足集团", "鸣鸣很忙")),
    ("fruit", "水果", ("水果", "鲜果", "果川", "鲜果优品")),
    ("bakery", "烘焙", ("面包", "烘焙", "蛋糕", "鹭岛面包", "面包店")),
    ("coffee_tea", "奶茶", ("沪上阿姨", "精选茶饮", "奶茶", "茶饮", "喜茶", "奈雪", "茶百道", "霸王茶姬")),
    ("coffee_tea", "咖啡", ("咖啡", "瑞幸", "星巴克", "Manner", "manner")),
    ("food_delivery", "饭", ("外卖", "餐饮", "餐馆", "小吃", "点餐订单", "包子", "鸡排", "老粉店", "美食", "饭", "粉大厨", "猪肉粉", "米粉", "盖码饭", "湘菜", "海鲜", "徐记海鲜", "饿了么", "麦当劳", "肯德基")),
    ("transport", "打车", ("滴滴", "打车", "曹操出行", "高德打车")),
    ("transport", "交通", ("地铁", "公交", "火车", "机票", "高铁")),
    ("stationery", "文具用品", ("学生用品", "文具", "记号笔", "辉煌学生用品店")),
    ("ecommerce", "网购", ("京东", "淘宝", "天猫", "拼多多", "抖音商城", "小红书", "快团团", "先用后付")),
    ("investment", "理财", ("基金", "理财", "定投", "申购", "赎回", "证券")),
    ("healthcare", "医疗", ("医院", "门诊", "药房", "体检")),
    ("digital_services", "数字服务", ("applegiftcard", "礼品卡", "会员订阅", "自动续费", "腾讯视频vip", "谱币充值", "云服务", "软件服务", "数字服务")),
    ("general_shopping", "日常购物", ("泡泡玛特", "日杂", "日用百货", "生活用品", "购物")),
    ("leisure_travel", "休闲旅行", ("橘子洲", "酒店", "民宿", "景区", "旅游")),
    ("lottery", "彩票", ("体彩", "福彩", "福利彩票", "彩票")),
    ("personal_transfer", "个人转账", ("向个人", "个人收款", "转账给", "个人转账")),
)

PERSONAL_TRANSFER_HINTS = ("向个人", "个人收款", "转账给", "个人转账", "扫二维码付款-给", "扫码付款给")


def normalize_matching_text(*values: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", "".join(value or "" for value in values))
    return re.sub(r"\s+", "", normalized).lower()


def resolved_result(category: str, thing: str, hint: str) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        thing=thing,
        confidence=0.95,
        source="local_rule",
        status="resolved",
        reason=f"local_rule:{category}:{hint}",
    )


def classify_locally(
    *,
    merchant: str | None,
    product: str | None,
    platform: str | None,
    payment_app: str | None,
    text: str,
) -> ClassificationResult:
    structured_text = normalize_matching_text(merchant, product)
    raw_text = normalize_matching_text(text)

    for category, thing, hints in LOCAL_CATEGORY_RULES:
        for hint in hints:
            if hint.lower() in structured_text:
                return resolved_result(category, thing, hint)

    for hint in PERSONAL_TRANSFER_HINTS:
        normalized_hint = normalize_matching_text(hint)
        if normalized_hint in structured_text or normalized_hint in raw_text:
            return resolved_result("personal_transfer", "个人转账", hint)

    return ClassificationResult(
        category="uncategorized",
        thing=None,
        confidence=0.0,
        source="none",
        status="pending",
        reason="local_rule:none",
    )


def detect_category_and_thing(text: str, product: str | None) -> tuple[str, str | None]:
    result = classify_locally(
        merchant=text,
        product=product,
        platform=None,
        payment_app=None,
        text="",
    )
    return result.category, result.thing
