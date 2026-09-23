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
    "healthcare": "医疗保健",
    "digital_services": "数字服务",
    "general_shopping": "日常购物",
    "leisure_travel": "休闲旅行",
    "lottery": "彩票",
    "personal_transfer": "个人转账",
    "apparel": "服饰装扮",
    "pet": "宠物",
    "beauty": "美容美发",
    "furniture_home": "家具家装",
    "maternal_child": "母婴亲子",
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
    ("apparel", "服饰装扮", ("优衣库", "ZARA", "H&M", "女装", "男装", "服装店", "鞋类", "箱包")),
    ("pet", "宠物", ("宠物医院", "宠物店", "猫粮", "狗粮", "宠物用品")),
    ("beauty", "美容美发", ("美容院", "理发店", "美发沙龙", "美甲")),
    ("furniture_home", "家具家装", ("宜家", "IKEA", "红星美凯龙", "家具城", "建材市场", "装修公司")),
    ("maternal_child", "母婴亲子", ("孩子王", "爱婴室", "母婴用品", "奶粉", "尿不湿", "纸尿裤", "童装")),
)

PERSONAL_TRANSFER_HINTS = ("向个人", "个人收款", "转账给", "个人转账", "扫二维码付款-给", "扫码付款给")


# 二级「垂类」字典。
#
# 一级 LOCAL_CATEGORY_RULES 命中的是具体商户/商品词（瑞幸、大麦网、停车费），
# 证据强，给 0.95。但中文工商名是无穷集合——「长沙湘怡文化发展有限公司」这种
# 永远枚举不完，再怎么往一级表里加词也追不上。
#
# 所以二级不认商户，只认**行业词**：营业执照名称里那段说明经营范围的成分。
# 证据弱一档，给 0.72，落库时同样是终态，但会被「待核实」挑出来让人复核。
# 只收录行业映射足够约定俗成的词；含糊的宁可留给模型，也不要在这里猜。
INDUSTRY_CATEGORY_RULES = (
    ("entertainment", "文娱消费", ("文化发展", "文化传播", "文化传媒", "文化艺术", "娱乐管理", "娱乐有限", "ktv", "量贩", "歌城", "酒吧", "清吧", "livehouse", "影城", "影院", "剧院", "剧场")),
    ("food_delivery", "餐饮", ("餐饮管理", "餐饮服务", "饮食管理", "食品经营", "餐厅", "食府", "酒楼", "茶餐厅")),
    ("healthcare", "医疗", ("大药房", "医药连锁", "医药有限", "诊所", "口腔", "眼科", "中医馆", "卫生服务")),
    ("education", "教育培训", ("教育科技", "教育咨询", "培训学校", "培训中心", "教育培训")),
    ("leisure_travel", "休闲旅行", ("酒店管理", "旅业", "旅行社", "民宿管理", "健身", "瑜伽", "游泳馆", "运动管理")),
    ("auto", "爱车养车", ("汽车服务", "汽车销售", "汽修", "车业", "汽车维修", "车服务")),
    ("digital_services", "数字服务", ("网络科技", "信息技术", "软件技术", "数码科技", "云计算")),
    ("general_shopping", "日常购物", ("百货", "商贸", "商业管理", "日用品", "生活馆")),
    ("property", "物业服务", ("物业管理", "置业管理", "房地产管理")),
    ("transport", "交通出行", ("客运", "运输服务", "汽车客运", "网络预约出租")),
    ("beauty", "美容美发", ("美容", "美发", "理发", "足浴", "spa")),
    ("furniture_home", "家具家装", ("家具", "建材", "装饰工程", "装修", "家居")),
    ("maternal_child", "母婴亲子", ("母婴用品", "孕婴童", "婴童")),
)

# 工商名里的地域前缀与组织形式后缀，匹配前先剥掉，
# 让「长沙湘怡文化发展有限公司」能以「湘怡文化发展」去撞词。
COMPANY_NAME_PREFIXES = (
    "北京", "上海", "天津", "重庆", "长沙", "湖南", "广州", "深圳", "广东", "杭州", "浙江",
    "南京", "江苏", "成都", "四川", "武汉", "湖北", "西安", "陕西", "郑州", "河南", "济南",
    "山东", "青岛", "合肥", "安徽", "福州", "厦门", "福建", "南昌", "江西", "昆明", "云南",
    "贵阳", "贵州", "南宁", "广西", "沈阳", "辽宁", "大连", "哈尔滨", "黑龙江", "长春", "吉林",
    "石家庄", "河北", "太原", "山西", "兰州", "甘肃", "银川", "宁夏", "西宁", "青海",
    "乌鲁木齐", "新疆", "呼和浩特", "内蒙古", "拉萨", "西藏", "海口", "三亚", "海南",
)
COMPANY_NAME_SUFFIXES = (
    "股份有限公司", "有限责任公司", "有限公司", "分公司", "总公司", "集团", "连锁",
    "管理有限", "服务有限", "经营部", "个体工商户", "工作室", "商行", "门店", "分店", "店",
)


def normalize_matching_text(*values: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", "".join(value or "" for value in values))
    return re.sub(r"\s+", "", normalized).lower()


def strip_company_noise(text: str) -> str:
    """
    剥掉工商名两端的地域前缀和组织形式后缀，只留下有辨识度的字号与经营范围。
    剥完为空就退回原串——「上海」这类整名就是地名的情况不能剥没了。
    """
    stripped = text
    for prefix in COMPANY_NAME_PREFIXES:
        if stripped.startswith(prefix) and len(stripped) > len(prefix):
            stripped = stripped[len(prefix):]
            break
    changed = True
    while changed:
        changed = False
        for suffix in COMPANY_NAME_SUFFIXES:
            if stripped.endswith(suffix) and len(stripped) > len(suffix):
                stripped = stripped[: -len(suffix)]
                changed = True
                break
    return stripped or text


def resolved_result(category: str, thing: str, hint: str) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        thing=thing,
        confidence=0.95,
        source="local_rule",
        status="resolved",
        reason=f"local_rule:{category}:{hint}",
    )


def industry_result(category: str, thing: str, hint: str) -> ClassificationResult:
    """行业词命中：同样是终态，但置信度低一档，好让「待核实」把它挑出来复核。"""
    return ClassificationResult(
        category=category,
        thing=thing,
        confidence=0.72,
        source="local_industry",
        status="resolved",
        reason=f"local_industry:{category}:{hint}",
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
    # 剥掉「长沙…有限公司」这类外壳后再撞一次，一级词也能多命中一批
    core_text = strip_company_noise(normalize_matching_text(merchant)) + normalize_matching_text(product)

    for category, thing, hints in LOCAL_CATEGORY_RULES:
        for hint in hints:
            lowered = hint.lower()
            if lowered in structured_text or lowered in core_text:
                return resolved_result(category, thing, hint)

    for hint in PERSONAL_TRANSFER_HINTS:
        normalized_hint = normalize_matching_text(hint)
        if normalized_hint in structured_text or normalized_hint in raw_text:
            return resolved_result("personal_transfer", "个人转账", hint)

    # 一级词没中，再拿行业词兜一层，避免直接掉进 pending 等模型
    for category, thing, hints in INDUSTRY_CATEGORY_RULES:
        for hint in hints:
            lowered = hint.lower()
            if lowered in structured_text or lowered in core_text:
                return industry_result(category, thing, hint)

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
