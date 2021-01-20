
import asyncio
import copy
import datetime
import json
import queue
import random
import re
import time
import traceback
from exceptions import ForbiddenError

import telepot
from printer import info as print
from reqs.custom import TopUserReq, QQReq
from reqs.utils import UtilsReq

from danmu.bili_abc import bili_danmu


class DanmuForward(bili_danmu.WsDanmuClient):
    manage_room_uid = None
    alive = set()
    not_alive = set()

    async def set_user(self, user):
        self.user = user
        self.GIFT_QUEUE = queue.Queue()
        self.is_live = False
        print(f'已关联用户{self.user.alias} -> {self._room_id}')
        await self._is_alive()
        print(self.user.tg_bot_token)
        self.bot = telepot.Bot(self.user.tg_bot_token)

    async def _is_alive(self):
        json_rsp = await self.user.req_s(UtilsReq.init_room, self.user, self._room_id)
        status = json_rsp.get('data', {}).get('live_status')
        self.is_live = status == 1
        return self.is_live

    async def forward_to_tg(self, text):
        self.bot.sendMessage(self.user.tg_channel, text, parse_mode='HTML')

    async def top_isalive(self):
        if not self.manage_room_uid:
            json_rsp = await self.user.req_s(UtilsReq.init_room, self.user, self._room_id)
            self.manage_room_uid = json_rsp.get('data').get('uid')

        page = 1
        data = []
        while(1):
            json_rsp = await TopUserReq.top_user(self.user, self._room_id, self.manage_room_uid, page)
            if page == 1:
                data += json_rsp.get('data').get('top3', [])
            data += json_rsp.get('data').get('list', [])
            if len(json_rsp.get('data').get('list', [])) < 29:
                break
            page += 1
            await asyncio.sleep(0.25)
        return data

    async def alert_top_live(self):
        while(1):
            try:
                data = await self.top_isalive()
            except ForbiddenError:
                print('请求top_live时403, 等待0.5h')
                await asyncio.sleep(60*30)
                continue
            alive = set([i.get('username') for i in data if i.get('is_alive')])
            # not_alive = set([i.get('username') for i in data if not i.get('is_alive')])
            # 新增观看 alive - self.alive
            # 不看了 self.alive - alive
            if alive != self.alive:
                await self.forward_to_tg(f"在线更新【{','.join(list(alive))}】")
                self.alive = alive
            await asyncio.sleep(self.user.top_live_delay)

    async def send_message_qq(self, target, messageChain, retry=3):
        if retry <= 0:
            return False
        # 获取session，判定是否可以用
        json_rsp = await self.user.req_s(QQReq.sendGroupMessage, self.user, self.user.qq_host, self.user.qq_session, target, messageChain)
        code = json_rsp.get('code')
        if code == 0:
            return json_rsp
        elif code == 3:
            # 需要verify,
            json_rsp = await self.user.req_s(QQReq.auth, self.user, self.user.qq_host, self.user.qq_key)
            self.user.qq_session = json_rsp.get('authKey')
            await self.user.req_s(QQReq.verify, self.user, self.user.qq_host, self.user.qq_num, self.user.qq_session)
            return self.send_message_qq(target, messageChain, retry-1)
        else:
            print(json_rsp)
            return json_rsp

        
    async def handle_danmu(self, data: dict):
        cmd = data['cmd']
        # print(data)
        open('log.log', 'a').write(str(data) + '\n')
        try:
            if cmd == 'DANMU_MSG':

                flag = data['info'][0][9]  # 获取弹幕类型， 0为普通弹幕
                info = data['info']
                danmu_content = info[1]  # 弹幕内容
                danmu_user = info[2]
                danmu_userid = danmu_user

                for group in self.user.at_all_group:
                    data = [
                        {"type": "AtAll"},
                        {"type": "Plain", "text": f"播了{self.is_live}"},
                        ]
                    await self.send_message_qq(group, data)

                data = {
                    'flag': flag,
                    'content': info[1],  # 弹幕内容
                    'sender_uid': info[2][0],  # 发送者uid
                    'sender_username': info[2][1],  # 发送者username,
                    'sender_bio_lv': info[3][0] if info[3] else '',  # 发送者牌子等级,
                    'sender_bio_name': info[3][1] if info[3] else '',  # 发送者牌子名称,
                    'sender_bio_roomid': info[3][3] if info[3] else '',  # 发送者牌子直播间,
                    'sender_time': datetime.datetime.fromtimestamp(info[9].get('ts')).strftime('%Y-%m-%d %H:%M:%S'),  # 发送时间
                }
                room = f'{self._room_id}'
                d = f"<u>{data['sender_bio_lv']}{data['sender_bio_name']}</u>{data['sender_username']}({data['sender_uid']})在{room}: {data['content']}"
                open('danmu.txt', 'a').write(d + '\n')
                if flag == 0:
                    print(d)
                    await self.forward_to_tg(d)

            elif cmd == 'SEND_GIFT':
                room_id = self._room_id
                user_id = data['data']['uid']
                username = data['data']['uname']

                gift_name = data['data']['giftName']
                gift_num = data['data']['num']
                coin_type = data['data']['coin_type']
                total_coin = data['data']['total_coin']

                data = {
                    'room': room_id,
                    'username': username,
                    'uid': user_id,
                    'gift_name': gift_name,
                    'gift_num': int(gift_num),
                    't': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'coin_type': coin_type,
                    'total_coin': total_coin,

                }
            elif cmd in ['COMBO_SEND']:
                # 礼物连送
                pass
            elif cmd == 'GUARD_BUY':
                # user_id=data['data']['uid'],
                username = data['data']['username']
                gift_name = data['data']['gift_name']
                gift_num = data['data']['num']
                d = f'{username}购买了{gift_num}个{gift_name}'
                await self.forward_to_tg(d)
            elif cmd in ['ONLINERANK', 'ONLINE_RANK_V2', 'PANEL', 'ROOM_RANK', 'ACTIVITY_BANNER_UPDATE_V2']:
                # 直播公告
                pass
            elif cmd in ['NOTICE_MSG']:
                # 礼物公告
                pass
            elif cmd in ['ROOM_REAL_TIME_MESSAGE_UPDATE', 'ROOM_BANNER', 'WIDGET_BANNER', 'ONLINE_RANK_COUNT', 'ONLINE_RANK_TOP3', ]:
                # 房间公告
                pass
            # elif cmd in ['WELCOME_GUARD', 'WELCOME', 'NOTICE_MSG', 'SYS_GIFT',
            #              'ACTIVITY_BANNER_UPDATE_BLS', 'ENTRY_EFFECT', 'ROOM_RANK',
            #              'ACTIVITY_BANNER_UPDATE_V2', 'COMBO_END', 'ROOM_REAL_TIME_MESSAGE_UPDATE',
            #              'ROOM_BLOCK_MSG', 'WISH_BOTTLE', 'WEEK_STAR_CLOCK', 'ROOM_BOX_MASTER',
            #              'HOUR_RANK_AWARDS', 'ROOM_SKIN_MSG', 'RAFFLE_START', 'RAFFLE_END',
            #              'GUARD_LOTTERY_START', 'GUARD_LOTTERY_END', 'GUARD_MSG',
            #              'USER_TOAST_MSG', 'SYS_MSG', 'COMBO_SEND', 'ROOM_BOX_USER',
            #              'TV_START', 'TV_END', 'ANCHOR_LOT_END', 'ANCHOR_LOT_AWARD',
            #              'ANCHOR_LOT_CHECKSTATUS', 'ANCHOR_LOT_STAR', 'ROOM_CHANGE',
            #              'new_anchor_reward', 'room_admin_entrance', 'ROOM_ADMINS', 'ANCHOR_LOT_START']:
            #     pass
            elif cmd in ['INTERACT_WORD']:
                # 推广
                pass
            elif cmd in ['ENTRY_EFFECT']:
                # {'cmd': 'ENTRY_EFFECT', 'data': {'id': 4, 'uid': 71401876, 'target_id': 514051814, 'mock_effect': 0, 'face': 'https://i0.hdslb.com/bfs/face/6f125a1cedcfa9fc12e87eb77a6c9d196e13c1e2.jpg', 'privilege_type': 3, 'copy_writing': '欢迎舰长 <%V-D-B%> 进入直播间', 'copy_color': '#ffffff', 'highlight_color': '#E6FF00', 'priority': 70, 'basemap_url': 'https://i0.hdslb.com/bfs/live/mlive/f34c7441cdbad86f76edebf74e60b59d2958f6ad.png', 'show_avatar': 1, 'effective_time': 2, 'web_basemap_url': '', 'web_effective_time': 0, 'web_effect_close': 0, 'web_close_time': 0, 'business': 1, 'copy_writing_v2': '欢迎舰长 <%V-D-B%> 进入直播间', 'icon_list': [], 'max_delay_time': 7}}
                # 进场消息
                pass
            elif cmd in ['WELCOME_GUARD']:
                # {'cmd': 'WELCOME_GUARD', 'data': {'uid': 71401876, 'username': 'V-D-B', 'guard_level': 3}}
                # 舰队进场
                pass
            elif cmd in ['LIVE']:
                d = f'开播 {self._room_id}'
                print(d)
                if not self.is_live:
                    for group in self.user.at_all_group:
                        data = [
                            {"type": "AtAll"},
                            {"type": "Plain", "text": "播了"},
                            ]
                        await self.send_message_qq(group, data)
                self.is_live = True
                await self.forward_to_tg(d)
            elif cmd in ['PREPARING']:
                d = f'下播 {self._room_id}'
                print(d)
                self.is_live = False
                await self.forward_to_tg(d)
            elif cmd.startswith('PK_'):
                pass
            else:
                print(data)
        except:
            traceback.print_exc()
            print(data)
        return True
