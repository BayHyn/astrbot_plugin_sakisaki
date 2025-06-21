import os
import json
import random
import time
import asyncio
import aiohttp

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

@register(
    "sakisaki",
    "LumineStory",
    "香草小祥小游戏插件，重构优化版",
    "1.5.0",
    "https://github.com/oyxning/astrbot_plugin_sakisaki"
)
class SakiSakiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        """
        插件初始化
        """
        super().__init__(context)
        self.config = config
        
        # 从配置初始化
        self._init_from_config()

        # 初始化数据文件路径
        self.data_path = os.path.join(self.context.get_data_dir(), "sakisaki_data.json")
        self.image_path = os.path.join(self.context.get_data_dir(), "sjp.jpg")

        # 初始化冷却字典
        self.user_cooldown = {}
        self.rank_cooldown = {}
        self.rank_queries = {}

        # 启动时检查并下载图片
        if not os.path.exists(self.image_path):
            asyncio.create_task(self._download_image())

    def _init_from_config(self):
        """
        从配置文件加载配置项
        """
        self.trigger_keywords = self.config.get("trigger_keywords", ["saki", "小祥"])
        self.success_rate = self.config.get("success_rate", 0.3)
        self.game_cooldown_time = self.config.get("game_cooldown", 60)
        self.rank_cooldown_time = self.config.get("rank_cooldown", 60)
        self.rank_query_limit = self.config.get("rank_query_limit", 3)
        self.image_url = self.config.get("image_url", "https://raw.githubusercontent.com/oyxning/astrbot_plugin_sakisaki/refs/heads/master/sjp.jpg")

    async def _download_image(self):
        """
        下载图片到插件数据目录
        """
        logger.info("检测到图片文件不存在，开始从网络下载...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.image_url) as resp:
                    if resp.status == 200:
                        with open(self.image_path, "wb") as f:
                            f.write(await resp.read())
                        logger.info(f"图片成功下载到: {self.image_path}")
                    else:
                        logger.error(f"图片下载失败，HTTP 状态码: {resp.status}")
        except Exception as e:
            logger.error(f"图片下载时发生异常: {e}")

    def _load_data(self):
        """
        从 JSON 文件加载数据
        """
        if not os.path.exists(self.data_path):
            return {"play_count": 0, "players": {}}
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载数据失败: {e}")
            return {"play_count": 0, "players": {}}

    def _save_data(self, data):
        """
        将数据保存到 JSON 文件
        """
        try:
            os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except IOError as e:
            logger.error(f"保存数据失败: {e}")
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """
        监听所有消息，用于关键词触发
        """
        msg = event.get_message_str()
        if not any(keyword in msg for keyword in self.trigger_keywords):
            return

        sender_id = event.get_sender_id()
        current_time = time.time()

        # 游戏冷却判断
        if sender_id in self.user_cooldown and current_time - self.user_cooldown[sender_id] < self.game_cooldown_time:
            # 在冷却时间内，不回复，避免刷屏
            return
        self.user_cooldown[sender_id] = current_time

        data = self._load_data()
        data["play_count"] = data.get("play_count", 0) + 1

        if random.random() < self.success_rate:
            # 成功追上
            players = data.setdefault("players", {})
            sender_info = players.setdefault(sender_id, {"name": event.get_sender_name(), "count": 0})
            sender_info["name"] = event.get_sender_name()  # 每次都更新昵称
            sender_info["count"] += 1
            
            self._save_data(data)
            
            yield event.plain_result(f"🎉 恭喜 {sender_info['name']} 追上了小祥！这是你第 {sender_info['count']} 次追上。")
            if os.path.exists(self.image_path):
                yield event.image_result(self.image_path)
            else:
                yield event.plain_result("（图片文件丢失了，请联系管理员检查）")
        else:
            # 失败
            self._save_data(data)
            yield event.plain_result("💨 可惜，这次让小祥溜走了~")

    @filter.command_group("saki", alias={"小祥"})
    async def saki_cmd_group(self):
        """saki 插件指令组"""
        pass

    @saki_cmd_group.command("排行榜", alias={"rank", "排行"})
    async def show_rank(self, event: AstrMessageEvent):
        """查看香草小祥排行榜"""
        sender_id = event.get_sender_id()
        current_time = time.time()

        # 排行榜查询冷却和次数限制
        if sender_id in self.rank_cooldown and current_time - self.rank_cooldown.get(sender_id, 0) < self.rank_cooldown_time:
            query_count = self.rank_queries.get(sender_id, 0)
            if query_count >= self.rank_query_limit:
                yield event.plain_result(f"⏳ 你在 {self.rank_cooldown_time}s 内的查询次数已达上限，请稍后再试！")
                return
            self.rank_queries[sender_id] = query_count + 1
        else:
            self.rank_cooldown[sender_id] = current_time
            self.rank_queries[sender_id] = 1

        data = self._load_data()
        players = data.get("players", {})
        if not players:
            yield event.plain_result("暂无玩家记录，快去追小祥吧~")
            return

        ranking = sorted(players.items(), key=lambda x: x[1]["count"], reverse=True)
        
        rank_msgs = ["🏆 香草小祥排行榜 🏆"]
        for i, (uid, info) in enumerate(ranking[:10], 1):
            rank_msgs.append(f"No.{i}: {info.get('name', '未知玩家')} - {info.get('count', 0)} 次")
        
        final_msg = "\n".join(rank_msgs)
        # 使用 text_to_image 渲染排行榜，更美观
        img_url = await self.text_to_image(final_msg)
        yield event.image_result(img_url)


    @saki_cmd_group.command("清除排行")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def clear_rank(self, event: AstrMessageEvent):
        """清除所有排行榜数据（仅管理员）"""
        self._save_data({"play_count": 0, "players": {}})
        logger.info(f"管理员 {event.get_sender_name()}({event.get_sender_id()}) 清除了排行榜数据")
        yield event.plain_result("🧹 排行榜数据已成功清除！")

    async def terminate(self):
        """
        插件卸载/停用时调用，用于释放资源
        """
        self.user_cooldown.clear()
        self.rank_cooldown.clear()
        self.rank_queries.clear()
        logger.info("SakiSaki 插件已卸载，相关内存数据已清理。")