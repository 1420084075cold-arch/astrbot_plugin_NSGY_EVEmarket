import requests
from typing import Optional

# ESI 基础地址
ESI_BASE = "https://esi.evetech.net/latest"

# 吉他市场参数
THE_FORGE = 10000002      # 吉他所在星域
JITA_STATION = 60003760   # 吉他 IV - 加达里海军后勤部空间站

def get_type_id -> Optional:
    """通过物品名称模糊搜索 type_id"""
    url = f"{ESI_BASE}/search/"
    params = {
        "categories": "inventory_type",
        "search": item_name,
        "strict": "false"
    }
    resp = requests.get
    resp.raise_for_status()
    data = resp.json()
    types = data.get
    return types if types else None

def get_type_name -> str:
    """根据 type_id 获取物品名称"""
    url = f"{ESI_BASE}/universe/types/{type_id}/"
    resp = requests.get
    resp.raise_for_status()
    return resp.json()

def get_jita_orders -> dict:
    """
    获取吉他空间站的买卖订单
    order_type: "buy" / "sell" / "all"
    """
    url = f"{ESI_BASE}/markets/{THE_FORGE}/orders/"
    params = {
        "datasource": "tranquility",
        "order_type": order_type,
        "type_id": type_id,
    }
    resp = requests.get
    resp.raise_for_status()
    orders = resp.json()

    # 筛出吉他空间站的订单
    jita_orders = [o for o in orders if o == JITA_STATION]
    return jita_orders

def parse_price -> dict:
    """从订单列表中提取最优买卖价"""
    sell_orders = [o for o in jita_orders if not o]
    buy_orders  = [o for o in jita_orders if o]

    best_sell = min if sell_orders else None
    best_buy  = max  if buy_orders  else None

    return {
        "buy":  best_buy  if best_buy  else None,
        "sell": best_sell if best_sell else None,
    }

def query_jita_price -> str:
    """主查询函数：输入物品名，返回格式化价格"""
    type_id = get_type_id
    if not type_id:
        return f"❌ 没找到 '{item_name}'，换个关键词试试？"

    full_name = get_type_name
    orders = get_jita_orders
    prices = parse_price

    if not prices and not prices:
        return f"📭 {full_name} 在吉他目前没有挂单。"

    result = f"【{full_name}】吉他市场价格：\n"
    if prices:
        result += f"买: {prices:,.2f} \n"
    if prices:
        result += f"卖: {prices:,.2f} "
    return result

# ===== 命令行入口 =====
if __name__ == "__main__":
    import sys
    if len > 1:
        item = " ".join
        print(query_jita_price)
    else:
        print
        print
