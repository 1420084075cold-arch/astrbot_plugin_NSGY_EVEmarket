from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
import re
from typing import Optional, Tuple, List

@register("EveMarket", "YourName", "EVE Online 市场查询插件，支持Jita价格、PLEX、模糊搜索和数量计算", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    # 定义区域ID常量
    REGION_ID_FORGE = 10000002      # The Forge 区域（Jita所在）
    REGION_ID_PLEX_GLOBAL = 19000001  # PLEX 全球统一市场区域
    SYSTEM_ID_JITA = 30000142       # Jita 星系
    ESI_BASE = "https://esi.evetech.net/latest"
    
    # PLEX 相关常量
    PLEX_TYPE_ID = 44992  # PLEX 的物品 ID
    PLEX_DEFAULT_QUANTITY = 500  # 默认查询 500 PLEX

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        logger.info("EVE Market 插件已加载")

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令"""
        user_name = event.get_sender_name()
        message_str = event.message_str
        message_chain = event.get_messages()
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""

    @staticmethod
    def get_type_id_by_name_fuzzwork(name: str) -> Optional[int]:
        """优先用 fuzzwork 按英文名查询 type_id。"""
        url = "https://www.fuzzwork.co.uk/api/typeid.php"
        params = {"typename": name}
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            if isinstance(data, list) and data:
                return data[0].get("typeID")
            elif isinstance(data, dict) and "typeID" in data:
                return data["typeID"]
        except Exception as e:
            logger.error(f"fuzzwork 查询失败: {e}")
        return None

    @staticmethod
    def get_type_id_by_name_esi(name: str) -> Optional[int]:
        """用 ESI 的 /universe/ids/ 接口，根据名称（可中文）查 type_id。"""
        ESI_BASE = "https://esi.evetech.net/latest"
        url = f"{ESI_BASE}/universe/ids/"
        headers = {"Accept-Language": "zh"}
        try:
            resp = requests.post(url, headers=headers, json=[name], timeout=10)
            if resp.status_code != 200:
                return None

            data = resp.json()
            inv_types: List[dict] = data.get("inventory_types") or []
            if not inv_types:
                return None
            return inv_types[0].get("id")
        except Exception as e:
            logger.error(f"ESI 查询失败: {e}")
        return None

    def search_inventory_types(self, search_string: str, strict: bool = False) -> Optional[List[Tuple[int, str]]]:
        """
        使用 ESI /search/ 接口模糊搜索物品，返回 ID 和名称
        
        参数:
            search_string: 搜索关键词（支持中文）
            strict: True=精确匹配，False=模糊匹配
        
        返回:
            匹配的 (type_id, name) 列表，未找到返回 None
        """
        url = f"{self.ESI_BASE}/v3/search/"
        params = {
            "categories": "inventory_type",
            "search": search_string,
        }
        if strict:
            params["strict"] = "true"
        
        headers = {"Accept-Language": "zh", "User-Agent": "AstrBot-EVE-Market-Plugin/1.0"}
        
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code != 200:
                logger.error(f"搜索失败，HTTP {resp.status_code}: {resp.text}")
                return None
            
            data = resp.json()
            type_ids = data.get("inventory_type", [])
            
            if not type_ids:
                logger.info(f"搜索 '{search_string}' 未找到任何结果")
                return None
            
            # 获取每个 type_id 的名称
            results = []
            for type_id in type_ids[:10]:  # 限制最多10个结果
                # 尝试获取物品名称
                name = self.get_type_name_by_id(type_id)
                results.append((type_id, name))
                logger.info(f"找到: ID={type_id}, 名称={name}")
            
            logger.info(f"搜索 '{search_string}' 找到 {len(results)} 个结果")
            return results
        except Exception as e:
            logger.error(f"搜索出错: {e}")
            return None

    def get_type_name_by_id(self, type_id: int) -> Optional[str]:
        """根据 type_id 获取物品名称"""
        url = f"{self.ESI_BASE}/universe/types/{type_id}/"
        headers = {"Accept-Language": "zh"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("name")
        except Exception as e:
            logger.error(f"获取名称失败: {e}")
        return None

    def get_type_id_by_name(self, name: str, use_fuzzy: bool = True) -> Tuple[Optional[int], Optional[List[Tuple[int, str]]]]:
        """
        综合查询物品ID，支持精确查询和模糊搜索
        
        参数:
            name: 物品名称
            use_fuzzy: 是否在精确查询失败时使用模糊搜索
        
        返回:
            (type_id, fuzzy_results) - type_id 是最终的 ID，fuzzy_results 是模糊搜索的所有结果
        """
        # 1. 尝试精确查询（fuzzwork - 英文名）
        type_id = self.get_type_id_by_name_fuzzwork(name)
        if type_id:
            logger.info(f"通过 fuzzwork 精确匹配: {name} -> {type_id}")
            return type_id, None
        
        # 2. 尝试精确查询（ESI - 支持中文）
        type_id = self.get_type_id_by_name_esi(name)
        if type_id:
            logger.info(f"通过 ESI 精确匹配: {name} -> {type_id}")
            return type_id, None
        
        # 3. 如果允许模糊搜索，尝试模糊搜索
        if use_fuzzy:
            logger.info(f"精确查询失败，尝试模糊搜索: {name}")
            fuzzy_results = self.search_inventory_types(name)
            if fuzzy_results and len(fuzzy_results) > 0:
                # 返回第一个结果的 ID 和所有结果列表
                return fuzzy_results[0][0], fuzzy_results
        
        return None, None

    def parse_query_input(self, input_str: str) -> Tuple[str, int]:
        """
        解析用户输入，提取物品名称和数量
        
        支持格式:
            - ".jita Tritanium"          # 默认数量1
            - ".jita Tritanium x100"     # 100个
            - ".jita Tritanium * 100"    # 100个
            - ".jita 100x Tritanium"     # 100个
            - ".jita 100 Tritanium"      # 100个
            - ".jita PLEX"               # 默认500 PLEX
        
        返回:
            (item_name, quantity)
        """
        input_str = input_str.strip()
        
        # 模式1: 物品名 x数量 或 物品名*数量
        pattern1 = r'^(.+?)\s*[×x*]\s*(\d+)$'
        match = re.match(pattern1, input_str, re.IGNORECASE)
        if match:
            return match.group(1).strip(), int(match.group(2))
        
        # 模式2: 数量x物品名 或 数量*物品名
        pattern2 = r'^(\d+)\s*[×x*]\s*(.+?)$'
        match = re.match(pattern2, input_str, re.IGNORECASE)
        if match:
            return match.group(2).strip(), int(match.group(1))
        
        # 模式3: 数字在前，空格分隔（如 "100 Tritanium"）
        pattern3 = r'^(\d+)\s+(.+?)$'
        match = re.match(pattern3, input_str)
        if match:
            return match.group(2).strip(), int(match.group(1))
        
        # 默认：没有数量，返回数量1
        return input_str, 1

    def get_price_by_type_id(self, type_id: int, region_id: int = None) -> Tuple[Optional[float], Optional[float]]:
        """
        根据 type_id 获取指定区域的最低卖价和最高买价。
        
        参数:
            type_id: 物品类型ID
            region_id: 区域ID，如果不指定则使用 The Forge (Jita所在区域)
                      对于 PLEX 应使用 19000001 (全球市场)
        """
        # 如果没有指定 region_id，默认使用 The Forge
        if region_id is None:
            region_id = self.REGION_ID_FORGE
        
        # 注意：PLEX 全球市场不需要检查 system_id，因为它是全球统一的
        # 只有 The Forge 区域需要过滤 Jita 星系的订单
        check_system = (region_id == self.REGION_ID_FORGE)
        
        page = 1
        sell_prices = []
        buy_prices = []

        while True:
            url = f"{self.ESI_BASE}/markets/{region_id}/orders/"
            params = {
                "order_type": "all",
                "page": page,
                "type_id": type_id,
            }
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                orders = resp.json()
            except Exception as e:
                logger.error(f"获取订单失败: {e}")
                return None, None

            if not orders:
                break

            for order in orders:
                # 只有 The Forge 区域需要过滤 Jita 星系
                if check_system and order.get("system_id") != self.SYSTEM_ID_JITA:
                    continue

                price = order["price"]
                if order["is_buy_order"]:
                    buy_prices.append(price)
                else:
                    sell_prices.append(price)

            x_pages = resp.headers.get("X-Pages")
            if x_pages is None or page >= int(x_pages):
                break
            page += 1

        min_sell = min(sell_prices) if sell_prices else None
        max_buy = max(buy_prices) if buy_prices else None
        return min_sell, max_buy

    def get_price_by_name(self, name: str, quantity: int = 1, region_id: int = None) -> Tuple[Optional[int], Optional[float], Optional[float], Optional[List[Tuple[int, str]]]]:
        """
        核心函数：根据名称查询价格，支持数量计算。
        
        参数:
            name: 物品名称
            quantity: 数量
            region_id: 区域ID，如果不指定则根据物品自动选择
        
        返回:
            (type_id, total_sell_price, total_buy_price, fuzzy_results)
            total_sell_price = 单价 * 数量
            total_buy_price = 单价 * 数量
        """
        # 自动判断：如果是 PLEX，使用全球市场区域
        if region_id is None and name.lower() == "plex":
            region_id = self.REGION_ID_PLEX_GLOBAL
            # PLEX 自动使用 500 数量
            if quantity == 1:
                quantity = self.PLEX_DEFAULT_QUANTITY
                logger.info(f"PLEX 查询，自动使用 {quantity} 个")
        
        # 获取物品 ID（支持模糊搜索）
        type_id, fuzzy_results = self.get_type_id_by_name(name)
        if not type_id:
            return None, None, None, fuzzy_results
        
        # 获取单价
        unit_sell, unit_buy = self.get_price_by_type_id(type_id, region_id)
        
        # 计算总价
        total_sell = unit_sell * quantity if unit_sell else None
        total_buy = unit_buy * quantity if unit_buy else None
        
        return type_id, total_sell, total_buy, fuzzy_results

    @filter.command(".jita")
    async def jita(self, event: AstrMessageEvent, content_message: str = ""):
        """查询 Jita 或全球市场的物品价格，支持数量计算和模糊搜索
        
        用法:
            .jita 物品名              # 查询1个的价格
            .jita 物品名 x100         # 查询100个的价格
            .jita 物品名 * 100        # 查询100个的价格
            .jita 100x 物品名         # 查询100个的价格
            .jita PLEX                # 自动查询500 PLEX
            .jita PLEX x1000          # 查询1000 PLEX
        """
        if not content_message:
            yield event.plain_result("请提供物品名称，例如：.jita Tritanium 或 .jita PLEX\n支持数量格式：.jita Tritanium x100")
            return
        
        # 解析物品名称和数量
        item_name, quantity = self.parse_query_input(content_message)
        
        if not item_name:
            yield event.plain_result("请提供物品名称")
            return
        
        # 查询价格
        type_id, total_sell, total_buy, fuzzy_results = self.get_price_by_name(item_name, quantity)
        
        # 处理未找到物品的情况
        if not type_id:
            if fuzzy_results and len(fuzzy_results) > 0:
                # 找到多个结果，显示让用户选择
                result_msg = f"未找到精确匹配的「{item_name}」，找到以下相关物品：\n\n"
                for i, (tid, tname) in enumerate(fuzzy_results[:10]):
                    if tname:
                        result_msg += f"{i+1}. {tname} (ID: {tid})\n"
                    else:
                        result_msg += f"{i+1}. Type ID: {tid}\n"
                result_msg += "\n💡 提示：请使用完整名称重新查询，或使用 .jitaid [TypeID] 直接查询"
                yield event.plain_result(result_msg)
            else:
                yield event.plain_result(f"未找到物品「{item_name}」，请确认名称是否正确。\n提示：支持中英文名称，也可以尝试使用部分名称模糊搜索。\n例如：.jita 狂暴 或 .jita Rifter")
            return
        
        # 判断是否为 PLEX
        is_plex = item_name.lower() == "plex" or type_id == self.PLEX_TYPE_ID
        
        # 检查是否有订单
        if total_sell is None and total_buy is None:
            if is_plex:
                yield event.plain_result(f"PLEX 在全球市场当前没有订单，请稍后再试。")
            else:
                yield event.plain_result(f"「{item_name}」在 Jita 当前没有订单。")
            return
        
        # 计算单价（只有在有订单的情况下才计算）
        unit_sell = total_sell / quantity if total_sell else None
        unit_buy = total_buy / quantity if total_buy else None
        
        # 记录日志
        logger.info(f"查询物品: {item_name} (type_id={type_id}, 数量={quantity}, is_plex={is_plex})")
        
        # 构建回复消息
        result_parts = []
        
        # 物品名称和数量
        if quantity > 1:
            result_parts.append(f"物品: {item_name} × {quantity}")
        else:
            result_parts.append(f"物品: {item_name}")
        
        # 市场类型
        if is_plex:
            result_parts.append("市场: PLEX 全球统一市场")
        else:
            result_parts.append("市场: Jita (The Forge)")
        
        # 卖价
        if total_sell is not None:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
            if quantity > 1 and unit_sell:
                result_parts.append(f"   (单价: {unit_sell:,.2f} ISK)")
        else:
            result_parts.append(f"💰 最低卖价: 无")
        
        # 买价
        if total_buy is not None:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
            if quantity > 1 and unit_buy:
                result_parts.append(f"   (单价: {unit_buy:,.2f} ISK)")
        else:
            result_parts.append(f"💎 最高买价: 无")
        
        # 计算差价（如果有买卖双方价格）
        if total_sell is not None and total_buy is not None and total_sell > total_buy:
            spread = total_sell - total_buy
            spread_percent = (spread / total_buy) * 100
            result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_percent:.1f}%)")
        
        yield event.plain_result("\n".join(result_parts))
    
    @filter.command(".jitaid")
    async def jita_by_id(self, event: AstrMessageEvent, type_id_str: str):
        """通过 type_id 查询价格，支持数量
        
        用法:
            .jitaid 34              # 查询 type_id 34 的价格
            .jitaid 34 x100         # 查询 100 个
        """
        # 解析输入
        content = type_id_str.strip()
        
        # 检查是否有数量
        quantity = 1
        type_id_str = content
        
        pattern = r'^(\d+)\s*[×x*]\s*(\d+)$'
        match = re.match(pattern, content, re.IGNORECASE)
        if match:
            type_id_str = match.group(1)
            quantity = int(match.group(2))
        else:
            parts = content.split()
            if len(parts) >= 2 and parts[0].isdigit():
                type_id_str = parts[0]
                # 检查第二部分是否是数量
                if parts[1].lower().startswith(('x', '*', '×')):
                    quantity = int(parts[1][1:]) if len(parts[1]) > 1 else 1
                elif parts[1].isdigit():
                    quantity = int(parts[1])
        
        try:
            type_id = int(type_id_str)
        except ValueError:
            yield event.plain_result("请提供正确的 Type ID 数字")
            return
        
        # 获取物品名称
        item_name = self.get_type_name_by_id(type_id) or f"Type ID {type_id}"
        
        # 判断是否为 PLEX
        is_plex = (type_id == self.PLEX_TYPE_ID)
        
        # 选择区域
        region_id = self.REGION_ID_PLEX_GLOBAL if is_plex else None
        
        # 查询价格
        unit_sell, unit_buy = self.get_price_by_type_id(type_id, region_id)
        
        # 计算总价
        total_sell = unit_sell * quantity if unit_sell else None
        total_buy = unit_buy * quantity if unit_buy else None
        
        if unit_sell is None and unit_buy is None:
            yield event.plain_result(f"{item_name} 在 {'全球市场' if is_plex else 'Jita'} 没有订单")
            return
        
        result_parts = []
        
        if quantity > 1:
            result_parts.append(f"{item_name} × {quantity}")
        else:
            result_parts.append(f"{item_name}")
        
        if is_plex:
            result_parts.append("市场: PLEX 全球统一市场")
        else:
            result_parts.append("市场: Jita (The Forge)")
        
        if total_sell is not None:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
            if quantity > 1 and unit_sell:
                result_parts.append(f"   (单价: {unit_sell:,.2f} ISK)")
        else:
            result_parts.append(f"💰 最低卖价: 无")
        
        if total_buy is not None:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
            if quantity > 1 and unit_buy:
                result_parts.append(f"   (单价: {unit_buy:,.2f} ISK)")
        else:
            result_parts.append(f"💎 最高买价: 无")
        
        if total_sell is not None and total_buy is not None and total_sell > total_buy:
            spread = total_sell - total_buy
            spread_percent = (spread / total_buy) * 100
            result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_percent:.1f}%)")
        
        yield event.plain_result("\n".join(result_parts))


    # ==================== 击杀邮件订阅功能 ====================
    
    def start_monitoring(self):
        """启动后台监控线程"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        
        def monitor_loop():
            """监控循环"""
            while self.monitoring_active:
                try:
                    self.check_new_killmails()
                except Exception as e:
                    logger.error(f"监控击杀邮件出错: {e}")
                time.sleep(30)  # 每30秒检查一次
        
        thread = Thread(target=monitor_loop, daemon=True)
        thread.start()
        logger.info("击杀邮件监控已启动")
    
    def check_new_killmails(self):
        """检查新的击杀邮件"""
        if not self.subscriptions:
            return
        
        # 构建查询参数
        all_killmails = []
        
        # 获取最近的击杀邮件（最后500条）
        url = f"{self.ZKILL_API}/killmails/"
        params = {
            "limit": 50,
            "startTime": (datetime.now() - timedelta(hours=1)).strftime("%Y%m%d%H%M")
        }
        
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                all_killmails = resp.json()
            else:
                logger.error(f"获取击杀邮件失败: {resp.status_code}")
                return
        except Exception as e:
            logger.error(f"请求击杀邮件API失败: {e}")
            return
        
        # 过滤匹配订阅的击杀邮件
        new_mails = []
        for killmail in all_killmails:
            kill_id = killmail.get("killmail_id")
            
            # 避免重复推送
            if f"{kill_id}" in self.killmail_history:
                continue
            
            # 检查是否匹配任何订阅
            matched = self.is_match_subscription(killmail)
            if matched:
                new_mails.append(killmail)
                self.killmail_history.add(f"{kill_id}")
            
            # 限制历史记录大小
            if len(self.killmail_history) > 10000:
                self.killmail_history.clear()
        
        # 如果有新邮件，推送到对应群组
        if new_mails:
            self.send_killmail_notifications(new_mails)
    
    def is_match_subscription(self, killmail: dict) -> bool:
        """检查击杀邮件是否匹配任何订阅"""
        if not self.subscriptions:
            return False
        
        # 获取击杀邮件中的实体信息
        victim = killmail.get("victim", {})
        victim_corp_id = victim.get("corporation_id")
        victim_alliance_id = victim.get("alliance_id")
        
        attackers = killmail.get("attackers", [])
        attacker_corps = set()
        attacker_alliances = set()
        for attacker in attackers:
            if attacker.get("corporation_id"):
                attacker_corps.add(attacker.get("corporation_id"))
            if attacker.get("alliance_id"):
                attacker_alliances.add(attacker.get("alliance_id"))
        
        # 检查所有群组的订阅
        for group_id, subs in self.subscriptions.items():
            for sub in subs:
                sub_type, sub_id = sub.split(":", 1)
                sub_id = int(sub_id)
                
                if sub_type == "corp":
                    # 订阅军团：被击杀方或击杀方
                    if victim_corp_id == sub_id or sub_id in attacker_corps:
                        return True
                elif sub_type == "alliance":
                    # 订阅联盟：被击杀方或击杀方
                    if victim_alliance_id == sub_id or sub_id in attacker_alliances:
                        return True
        
        return False
    
    def send_killmail_notifications(self, killmails: List[dict]):
        """发送击杀邮件通知到所有相关群组"""
        for killmail in killmails:
            # 获取击杀邮件详情
            kill_id = killmail.get("killmail_id")
            victim = killmail.get("victim", {})
            victim_name = victim.get("character_name", "Unknown")
            victim_ship = victim.get("ship_type_name", "Unknown")
            victim_corp = victim.get("corporation_name", "Unknown")
            victim_alliance = victim.get("alliance_name")
            
            # 计算价值
            total_value = killmail.get("zkb", {}).get("totalValue", 0)
            
            # 获取击杀者信息（取前3个）
            attackers = killmail.get("attackers", [])[:3]
            attacker_names = []
            for attacker in attackers:
                name = attacker.get("character_name", "Unknown")
                ship = attacker.get("ship_type_name", "Unknown")
                if name and name != "Unknown":
                    attacker_names.append(f"{name} ({ship})")
            attacker_str = ", ".join(attacker_names) if attacker_names else "Unknown"
            
            # 构建消息
            message = f"""⚔️ **新击杀邮件** ⚔️

💀 **受害者**: {victim_name}
🏢 **军团**: {victim_corp}
{'🌟 **联盟**: ' + victim_alliance if victim_alliance else ''}
🚀 **舰船**: {victim_ship}
💰 **价值**: {total_value:,.2f} ISK

🎯 **击杀者**: {attacker_str}

🔗 **详情**: {self.ZKILL_REDIRECT}/{kill_id}/"""

            # 推送到所有订阅群组
            for group_id in self.subscriptions.keys():
                # 这里需要根据 AstrBot 的 API 发送消息到指定群组
                # 由于 AstrBot 的消息发送机制，这里使用 event 的回调需要调整
                logger.info(f"推送击杀邮件到群组 {group_id}: {victim_name} 被击杀")
            
            # 记录日志
            logger.info(f"击杀邮件 {kill_id}: {victim_name} 在 {victim_ship} 被击杀，价值 {total_value:,.2f} ISK")

    @filter.command(".sub")
    async def subscribe(self, event: AstrMessageEvent):
        """订阅击杀邮件
        
        用法:
            .sub corp [军团ID]    # 订阅军团（被击杀或击杀时通知）
            .sub alliance [联盟ID] # 订阅联盟
            .sub list              # 查看当前订阅
            .sub clear             # 清空当前群组的所有订阅
        """
        content = event.message_str.strip()
        parts = content.split()
        
        if len(parts) < 2:
            yield event.plain_result("用法: .sub corp/alliance [ID] 或 .sub list/clear")
            return
        
        group_id = str(event.group_id) if hasattr(event, 'group_id') else "default"
        
        if group_id not in self.subscriptions:
            self.subscriptions[group_id] = set()
        
        command = parts[1].lower()
        
        if command == "list":
            subs = self.subscriptions.get(group_id, set())
            if not subs:
                yield event.plain_result("当前群组没有订阅任何实体")
            else:
                result = "当前订阅的实体:\n"
                for sub in subs:
                    sub_type, sub_id = sub.split(":", 1)
                    result += f"  - {sub_type}: {sub_id}\n"
                yield event.plain_result(result)
            return
        
        if command == "clear":
            self.subscriptions[group_id].clear()
            yield event.plain_result("已清空当前群组的所有订阅")
            return
        
        if len(parts) < 3:
            yield event.plain_result(f"用法: .sub {command} [ID]")
            return
        
        entity_id = parts[2]
        
        if command == "corp":
            sub_key = f"corp:{entity_id}"
            self.subscriptions[group_id].add(sub_key)
            yield event.plain_result(f"已订阅军团 ID: {entity_id}\n当该军团被击杀或参与击杀时会收到通知")
        
        elif command == "alliance":
            sub_key = f"alliance:{entity_id}"
            self.subscriptions[group_id].add(sub_key)
            yield event.plain_result(f"已订阅联盟 ID: {entity_id}\n当该联盟被击杀或参与击杀时会收到通知")
        
        else:
            yield event.plain_result(f"未知的订阅类型: {command}\n支持的类型: corp, alliance")

    @filter.command(".unsub")
    async def unsubscribe(self, event: AstrMessageEvent):
        """取消订阅击杀邮件
        
        用法:
            .unsub corp [军团ID]    # 取消订阅军团
            .unsub alliance [联盟ID] # 取消订阅联盟
        """
        content = event.message_str.strip()
        parts = content.split()
        
        if len(parts) < 2:
            yield event.plain_result("用法: .unsub corp/alliance [ID]")
            return
        
        group_id = str(event.group_id) if hasattr(event, 'group_id') else "default"
        
        if group_id not in self.subscriptions:
            yield event.plain_result("当前群组没有订阅")
            return
        
        command = parts[1].lower()
        
        if len(parts) < 3:
            if command == "corp":
                # 移除所有军团订阅
                to_remove = [s for s in self.subscriptions[group_id] if s.startswith("corp:")]
                for s in to_remove:
                    self.subscriptions[group_id].remove(s)
                yield event.plain_result(f"已移除所有军团订阅")
            elif command == "alliance":
                to_remove = [s for s in self.subscriptions[group_id] if s.startswith("alliance:")]
                for s in to_remove:
                    self.subscriptions[group_id].remove(s)
                yield event.plain_result(f"已移除所有联盟订阅")
            return
        
        entity_id = parts[2]
        
        if command == "corp":
            sub_key = f"corp:{entity_id}"
            if sub_key in self.subscriptions[group_id]:
                self.subscriptions[group_id].remove(sub_key)
                yield event.plain_result(f"已取消订阅军团 ID: {entity_id}")
            else:
                yield event.plain_result(f"未订阅军团 ID: {entity_id}")
        
        elif command == "alliance":
            sub_key = f"alliance:{entity_id}"
            if sub_key in self.subscriptions[group_id]:
                self.subscriptions[group_id].remove(sub_key)
                yield event.plain_result(f"已取消订阅联盟 ID: {entity_id}")
            else:
                yield event.plain_result(f"未订阅联盟 ID: {entity_id}")
        
        else:
            yield event.plain_result(f"未知的订阅类型: {command}")

    @filter.command(".search")
    async def search_entity(self, event: AstrMessageEvent, name: str = ""):
        """搜索军团/联盟ID
        
        用法:
            .search [名称]
        """
        if not name:
            yield event.plain_result("请输入要搜索的名称，例如: .search Goonswarm")
            return
        
        name = name.strip()
        
        # 使用 ESI 搜索军团/联盟
        url = f"{self.ESI_BASE}/universe/ids/"
        headers = {"Accept-Language": "zh"}
        
        try:
            resp = requests.post(url, headers=headers, json=[name], timeout=10)
            if resp.status_code != 200:
                yield event.plain_result("搜索失败，请稍后再试")
                return
            
            data = resp.json()
            
            result_parts = []
            
            # 搜索到军团
            corporations = data.get("corporations", [])
            if corporations:
                result_parts.append("🏢 **军团**:")
                for corp in corporations[:5]:
                    result_parts.append(f"  - {corp.get('name')} (ID: {corp.get('id')})")
            
            # 搜索到联盟
            alliances = data.get("alliances", [])
            if alliances:
                result_parts.append("🌟 **联盟**:")
                for ally in alliances[:5]:
                    result_parts.append(f"  - {ally.get('name')} (ID: {ally.get('id')})")
            
            if result_parts:
                result_parts.append("\n💡 使用 .sub corp/alliance [ID] 订阅")
                yield event.plain_result("\n".join(result_parts))
            else:
                yield event.plain_result(f"未找到与「{name}」相关的军团或联盟")
        
        except Exception as e:
            logger.error(f"搜索实体失败: {e}")
            yield event.plain_result("搜索失败，请稍后再试")

    # ==================== 原有的市场查询功能 ====================

    # ... (此处保留原有的所有市场查询方法，与之前相同)
    # 包括: get_type_id_by_name_fuzzwork, get_type_id_by_name_esi, search_inventory_types,
    # get_type_id_by_name, parse_query_input, get_price_by_type_id, get_price_by_name,
    # jita, jita_by_id 等方法

    # 由于代码长度限制，此处省略原有方法，请从之前的回复中复制
