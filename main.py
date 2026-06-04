from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
import re
from typing import Optional, Tuple, List

@register("EveMarket", "YourName", "EVE Online Jita 市场查询插件", "1.0.0")
class EveMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    REGION_ID_FORGE = 10000002
    REGION_ID_PLEX_GLOBAL = 19000001  # PLEX 全球市场区域ID
    SYSTEM_ID_JITA = 30000142
    ESI_BASE = "https://esi.evetech.net/latest"
    
    PLEX_TYPE_ID = 44992
    
    # 中英文映射
    CN_TO_EN = {
        "三钛合金": "Tritanium",
        "类晶体胶矿": "Mexallon",
        "类银超金属": "Pyerite",
        "同位聚合体": "Isogen",
        "超新星诺克石": "Nocxium",
        "晶状石英核岩": "Megacyte",
        "超噬矿": "Zydrine",
        "伊甸币": "Plex",
        "狂怒者级": "Vexor",
        "毒蜥级": "Gila",
        "伊什塔级": "Ishtar",
        "圣光": "Saint",
        "护符": "Talisman",
        "水晶": "Crystal",
        "蝰蛇": "Viper",
        "强势": "Potent",
        "九头蛇": "Hydra",
        "阿斯克雷": "Asklepian",
    }
    
    # 脑插级别
    IMPLANT_GRADES = {
        "阿尔法": "Alpha",
        "贝它": "Beta",
        "伽玛": "Gamma",
        "德尔塔": "Delta",
        "伊普西隆": "Epsilon",
        "欧米伽": "Omega",
    }

    async def initialize(self):
        logger.info("EVE Market 插件已加载")

    async def terminate(self):
        logger.info("EVE Market 插件已卸载")

    # ==================== 核心查询方法 ====================
    
    def get_type_id(self, name: str) -> Optional[int]:
        """获取物品 Type ID"""
        try:
            url = "https://www.fuzzwork.co.uk/api/typeid.php"
            r = requests.get(url, params={"typename": name}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    return data[0].get("typeID")
                elif isinstance(data, dict) and "typeID" in data:
                    return data["typeID"]
        except Exception as e:
            logger.error(f"查询失败: {e}")
        return None

    def search_fuzzy(self, keyword: str) -> List[Tuple[int, str]]:
        """模糊搜索物品"""
        try:
            url = f"{self.ESI_BASE}/universe/ids/"
            headers = {"Accept-Language": "zh"}
            resp = requests.post(url, headers=headers, json=[keyword], timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("inventory_types", []):
                    results.append((item.get("id"), item.get("name")))
                return results
        except Exception as e:
            logger.error(f"搜索失败: {e}")
        return []

    def smart_search(self, keyword: str) -> Tuple[Optional[int], Optional[str], List[Tuple[int, str]]]:
        """智能搜索：支持中文、英文、脑插、模糊匹配"""
        keyword = keyword.strip()
        
        # 1. PLEX
        if keyword.lower() in ["plex", "伊甸币"]:
            return self.PLEX_TYPE_ID, "PLEX", []
        
        # 2. 脑插处理
        for cn_series, en_series in self.CN_TO_EN.items():
            for cn_grade, en_grade in self.IMPLANT_GRADES.items():
                if keyword in [f"{cn_series}{cn_grade}型", f"{cn_series}-{cn_grade}型"]:
                    en_name = f"'{en_series}' {en_grade}"
                    type_id = self.get_type_id(en_name)
                    if type_id:
                        return type_id, f"{cn_series}{cn_grade}型", []
        
        # 3. 直接搜索英文脑插
        match = re.match(r"^'(.+)'\s+(Alpha|Beta|Gamma|Delta|Epsilon|Omega)$", keyword)
        if match:
            type_id = self.get_type_id(keyword)
            if type_id:
                return type_id, keyword, []
        
        # 4. 中文映射
        if keyword in self.CN_TO_EN:
            en_name = self.CN_TO_EN[keyword]
            type_id = self.get_type_id(en_name)
            if type_id:
                return type_id, en_name, []
        
        # 5. 直接搜索
        type_id = self.get_type_id(keyword)
        if type_id:
            return type_id, keyword, []
        
        # 6. 模糊搜索
        results = self.search_fuzzy(keyword)
        if results:
            return results[0][0], results[0][1], results
        
        return None, None, []

    def get_price(self, type_id: int) -> Tuple[Optional[float], Optional[float], bool]:
        """获取价格，返回 (卖价, 买价, 是否为PLEX)"""
        if type_id == self.PLEX_TYPE_ID:
            return self.get_plex_price(), True
        return self.get_jita_price(type_id), False

    def get_plex_price(self) -> Tuple[Optional[float], Optional[float]]:
        """获取 PLEX 全球市场价格"""
        sell_prices = []
        buy_prices = []
        page = 1
        max_pages = 5
        
        try:
            for page in range(1, max_pages + 1):
                url = f"{self.ESI_BASE}/markets/{self.REGION_ID_PLEX_GLOBAL}/orders/"
                params = {"page": page, "type_id": self.PLEX_TYPE_ID, "order_type": "all"}
                
                resp = requests.get(url, params=params, timeout=15)
                
                if resp.status_code == 404:
                    logger.warning("PLEX 市场区域不存在或没有订单")
                    break
                elif resp.status_code != 200:
                    logger.error(f"获取PLEX订单失败: HTTP {resp.status_code}")
                    break
                
                orders = resp.json()
                if not orders:
                    break
                
                for order in orders:
                    price = order.get("price")
                    if price is None:
                        continue
                    if order.get("is_buy_order"):
                        buy_prices.append(price)
                    else:
                        sell_prices.append(price)
                
                # 检查是否还有下一页
                if "X-Pages" in resp.headers:
                    total_pages = int(resp.headers["X-Pages"])
                    if page >= total_pages:
                        break
                    
        except requests.exceptions.Timeout:
            logger.error("PLEX 查询超时")
        except Exception as e:
            logger.error(f"PLEX 查询异常: {e}")
        
        # 如果还是没有数据，尝试不限定 type_id 查询整个市场（调试用）
        if not sell_prices and not buy_prices:
            logger.info("PLEX 专用市场无数据，尝试查询区域所有订单...")
            try:
                url = f"{self.ESI_BASE}/markets/{self.REGION_ID_PLEX_GLOBAL}/orders/"
                resp = requests.get(url, params={"page": 1, "order_type": "all"}, timeout=15)
                if resp.status_code == 200:
                    orders = resp.json()
                    logger.info(f"PLEX 市场返回 {len(orders)} 条订单")
                    for order in orders:
                        if order.get("type_id") == self.PLEX_TYPE_ID:
                            price = order.get("price")
                            if order.get("is_buy_order"):
                                buy_prices.append(price)
                            else:
                                sell_prices.append(price)
            except Exception as e:
                logger.error(f"PLEX 备选查询失败: {e}")
        
        min_sell = min(sell_prices) if sell_prices else None
        max_buy = max(buy_prices) if buy_prices else None
        
        if min_sell is None and max_buy is None:
            logger.warning("PLEX 完全没有订单数据")
        
        return min_sell, max_buy

    def get_jita_price(self, type_id: int) -> Tuple[Optional[float], Optional[float]]:
        """获取 Jita 市场价格"""
        sell_prices = []
        buy_prices = []
        page = 1
        
        try:
            while True:
                url = f"{self.ESI_BASE}/markets/{self.REGION_ID_FORGE}/orders/"
                params = {"page": page, "type_id": type_id, "order_type": "all"}
                
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code != 200:
                    break
                
                orders = resp.json()
                if not orders:
                    break
                
                for order in orders:
                    if order.get("system_id") != self.SYSTEM_ID_JITA:
                        continue
                    price = order.get("price")
                    if price is None:
                        continue
                    if order.get("is_buy_order"):
                        buy_prices.append(price)
                    else:
                        sell_prices.append(price)
                
                if "X-Pages" in resp.headers:
                    total_pages = int(resp.headers["X-Pages"])
                    if page >= total_pages:
                        break
                page += 1
                
        except Exception as e:
            logger.error(f"获取Jita订单失败: {e}")
        
        min_sell = min(sell_prices) if sell_prices else None
        max_buy = max(buy_prices) if buy_prices else None
        return min_sell, max_buy

    def parse_input(self, input_str: str) -> Tuple[str, int]:
        """解析物品名称和数量"""
        input_str = input_str.strip()
        
        match = re.match(r'^(.+?)\s*[×x*]\s*(\d+)$', input_str, re.IGNORECASE)
        if match:
            return match.group(1).strip(), int(match.group(2))
        
        match = re.match(r'^(\d+)\s*[×x*]\s*(.+?)$', input_str, re.IGNORECASE)
        if match:
            return match.group(2).strip(), int(match.group(1))
        
        match = re.match(r'^(\d+)\s+(.+?)$', input_str)
        if match:
            return match.group(2).strip(), int(match.group(1))
        
        return input_str, 1

    # ==================== 主命令 ====================
    
    @filter.command(".jita")
    async def jita(self, event: AstrMessageEvent, content: str = ""):
        """查询 Jita 市场价格"""
        if not content:
            yield event.plain_result(
                "📋 **Jita 市场查询**\n\n"
                "用法: .jita [物品名]\n"
                "      .jita [物品名] x[数量]\n\n"
                "📖 示例:\n"
                "  【矿物】.jita 三钛合金\n"
                "  【舰船】.jita 狂怒者级\n"
                "  【PLEX】.jita PLEX\n"
                "  【批量】.jita PLEX x100\n"
                "  【脑插】.jita 圣光阿尔法型\n\n"
                "💡 支持中英文名称，自动识别 PLEX 和脑插"
            )
            return
        
        item_name, quantity = self.parse_input(content)
        
        if not item_name:
            yield event.plain_result("❌ 请提供物品名称")
            return
        
        yield event.plain_result(f"🔍 正在查询「{item_name}」...")
        
        type_id, actual_name, suggestions = self.smart_search(item_name)
        
        if not type_id:
            if suggestions:
                msg = f"❌ 未找到「{item_name}」，相关物品：\n\n"
                for tid, tname in suggestions[:5]:
                    msg += f"  • {tname}\n"
                    msg += f"    查询: .jitaid {tid}\n\n"
                msg += "💡 使用更完整的名称重试"
                yield event.plain_result(msg)
            else:
                yield event.plain_result(
                    f"❌ 未找到「{item_name}」\n\n"
                    f"💡 尝试:\n"
                    f"  - 矿物: .jita 三钛合金\n"
                    f"  - 舰船: .jita 狂怒者级\n"
                    f"  - 脑插: .jita 圣光阿尔法型\n"
                    f"  - 英文: .jita Tritanium"
                )
            return
        
        (sell, buy), is_plex = self.get_price(type_id)
        
        # 调试日志
        logger.info(f"查询 {actual_name}: 卖价={sell}, 买价={buy}, is_plex={is_plex}")
        
        if sell is None and buy is None:
            if is_plex:
                yield event.plain_result(
                    f"⚠️ PLEX 全球市场暂时无订单\n\n"
                    f"可能原因:\n"
                    f"  - ESI API 数据延迟\n"
                    f"  - 全球市场区域ID可能已变更\n"
                    f"  - 请稍后再试\n\n"
                    f"💡 尝试使用 .jitaid {self.PLEX_TYPE_ID} 直接查询"
                )
            else:
                yield event.plain_result(f"「{actual_name}」在 Jita 没有公开订单")
            return
        
        total_sell = sell * quantity if sell else None
        total_buy = buy * quantity if buy else None
        
        # 判断是否是脑插
        is_implant = False
        implant_slot = ""
        for cn_grade in self.IMPLANT_GRADES.keys():
            if cn_grade in actual_name:
                is_implant = True
                slot_map = {"阿尔法": "1号(感知)", "贝它": "2号(记忆)", "伽玛": "3号(毅力)", 
                           "德尔塔": "4号(智力)", "伊普西隆": "5号(魅力)", "欧米伽": "6号(套装)"}
                implant_slot = slot_map.get(cn_grade, "")
                break
        
        # 构建返回消息
        if is_plex:
            result_parts = [
                "🌍 **PLEX 全球市场**",
                f"📦 **PLEX**" + (f" x {quantity}" if quantity > 1 else ""),
                "",
            ]
        else:
            result_parts = [
                f"📍 **Jita 市场**",
                f"📦 **{actual_name}**" + (f" x {quantity}" if quantity > 1 else ""),
            ]
            if is_implant and implant_slot:
                result_parts.append(f"🔌 插槽: {implant_slot}")
            result_parts.append("")
        
        if total_sell:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
            if quantity > 1 and sell:
                result_parts.append(f"   (单价: {sell:,.2f} ISK)")
        else:
            result_parts.append(f"💰 最低卖价: 无订单")
        
        if total_buy:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
            if quantity > 1 and buy:
                result_parts.append(f"   (单价: {buy:,.2f} ISK)")
        else:
            result_parts.append(f"💎 最高买价: 无订单")
        
        if sell and buy:
            spread = sell - buy
            spread_pct = (spread / buy) * 100
            result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
        if is_implant and "欧米伽" not in actual_name:
            for cn_series in self.CN_TO_EN.keys():
                if cn_series in actual_name:
                    result_parts.append(f"\n💡 查询全套: .jita {cn_series}阿尔法型（需逐个查询）")
                    break
        
        yield event.plain_result("\n".join(result_parts))

    @filter.command(".jitaid")
    async def jita_by_id(self, event: AstrMessageEvent, type_id_str: str):
        """通过 Type ID 查询价格"""
        try:
            type_id = int(type_id_str.strip())
        except ValueError:
            yield event.plain_result("❌ 请提供正确的 Type ID 数字")
            return
        
        (sell, buy), is_plex = self.get_price(type_id)
        
        if sell is None and buy is None:
            if is_plex:
                yield event.plain_result(f"PLEX (ID: {type_id}) 全球市场暂时无订单")
            else:
                yield event.plain_result(f"Type ID {type_id} 在 Jita 没有订单")
            return
        
        if is_plex:
            result_parts = [
                "🌍 **PLEX 全球市场**",
                f"📦 **Type ID: {type_id} (PLEX)**",
                "",
            ]
        else:
            result_parts = [
                "📍 **Jita 市场**",
                f"📦 **Type ID: {type_id}**",
                "",
            ]
        
        if sell:
            result_parts.append(f"💰 最低卖价: {sell:,.2f} ISK")
        if buy:
            result_parts.append(f"💎 最高买价: {buy:,.2f} ISK")
        
        if sell and buy:
            spread = sell - buy
            spread_pct = (spread / buy) * 100
            result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
        yield event.plain_result("\n".join(result_parts))
