from .bili_danmu import WsDanmuClient
import asyncio
import traceback
import json
import copy
import datetime
import random
import time
import queue
from printer import info as print
from reqs.utils import UtilsReq


class DanmuGiftThx(WsDanmuClient):

    # GIFT_MSG = '谢谢可爱的{username}投喂{giftname}x{num} (╭￣3￣)╭♡'
    # DELAY_SECOND = 3

    async def set_user(self, user):
        self.user = user
        self.GIFT_QUEUE = queue.Queue()
        self.is_live = False
        print(f'已关联用户{self.user.alias} -> {self._room_id}')
        await self._is_alive()

    async def _is_alive(self):
        json_rsp = await self.user.req_s(UtilsReq.init_room, self.user, self._room_id)
        status = json_rsp.get('data', {}).get('live_status')
        self.is_live = status == 1
        return self.is_live

    async def run_alter(self):
        if len(self.user.alerts) == 0:
            print('感谢🐔公告循环内容为空')
            return
        now = 0

        while(1):
            if self.is_live:
                text = self.user.alerts[now % len(self.user.alerts)]
                await self.send_danmu(text)
                now += 1
            else:
                print(f'{self._room_id}未开播, {datetime.datetime.now()}')
            await asyncio.sleep(self.user.alert_second)

    async def run_medal_update(self):
        json_rsp = await self.user.req_s(UtilsReq.get_room_info, self.user, self._room_id)
        uid = json_rsp.get('data', {}).get('uid', 0)

        if uid == 0:
            print('获取uid失败，重启或检查房间号')
            return

        if not self.user.medal_update_format:
            print('medal_update_format未定义，勋章升级提醒关闭')
            return

        async def get_medals():
            medal_data = {}
            json_rsp = await self.user.req_s(UtilsReq.get_room_medal, self.user, self._room_id, uid, 1)
            total_page = json_rsp.get('data', {}).get('total_page', 1)
            medal_data.update({x.get('uid'): {'level': x.get('level'), 'uname': x.get('uname')}
                               for x in json_rsp.get('data', {}).get('list', [])})
            if total_page > 1:
                for p in range(2, total_page+1):
                    json_rsp = await self.user.req_s(UtilsReq.get_room_medal, self.user, self._room_id, uid, p)
                    medal_data.update({x.get('uid'): {'level': x.get('level'), 'uname': x.get(
                        'uname')} for x in json_rsp.get('data', {}).get('list', [])})
            return medal_data

        medal_rank_already = await get_medals()

        while(1):
            try:
                medal_rank = copy.deepcopy(await get_medals())
                # print(f'already={medal_rank_already}')
                # print(f'new={medal_rank}')
                for mid, info in medal_rank.items():
                    if mid not in medal_rank_already:
                        # 牌子新获取
                        uname = medal_rank[mid].get('uname')
                        new_level = medal_rank[mid].get('level')
                        old_level = 0
                        await self.send_danmu(self.user.medal_update_format.format(username=uname, uid=mid, new_level=new_level, old_level=old_level))
                    elif mid in medal_rank_already and info.get('level', 0) > medal_rank_already[mid].get('level', 0):
                        # 牌子升级
                        uname = medal_rank[mid].get('uname')
                        new_level = medal_rank[mid].get('level')
                        old_level = medal_rank_already[mid].get('level', 0)

                        await self.send_danmu(self.user.medal_update_format.format(username=uname, uid=mid, new_level=new_level, old_level=old_level))
                    else:
                        pass
                medal_rank_already = copy.deepcopy(medal_rank)

            except:
                traceback.print_exc()
            await asyncio.sleep(self.user.medal_update_check_delay)

    async def run_fans(self):
        # 获取uid
        json_rsp = await self.user.req_s(UtilsReq.get_room_info, self.user, self._room_id)
        uid = json_rsp.get('data', {}).get('uid', 0)

        if uid == 0:
            print('获取uid失败，重启或检查房间号')
            return
        fans_already = set()
        now = int(time.time())
        while(1):
            try:
                json_rsp = await self.user.req_s(UtilsReq.get_user_follower, self.user, uid)
                # print(json_rsp)
                fans = json_rsp.get('data', {}).get('list', [])
                for u in fans:
                    mid = u.get('mid', 0)
                    mtime = u.get('mtime', 0)
                    uname = u.get('uname', '')
                    if uname and mid and mtime:
                        if mtime < now:
                            continue
                        if mid in fans_already:
                            continue
                        await self.send_danmu(self.user.focus_thx_format.format(username=uname,
                                                                                random1=random.choice(
                                                                                    self.user.random_list_1),
                                                                                random2=random.choice(
                                                                                    self.user.random_list_2),
                                                                                random3=random.choice(self.user.random_list_3)))
                        fans_already.add(mid)
            except:
                traceback.print_exc()
            await asyncio.sleep(self.user.fans_check_delay)

    async def run_sender(self):
        roomid = self._room_id
        wait_to_send_danmu = {}     # 礼物列表合并后的输出
        sem = asyncio.Semaphore(1)
        while(1):
            # 取出所有结果，添加到等待队列
            # 如果某个room-user-gift保持了5s不动，则推出
            async with sem:
                qlength = self.GIFT_QUEUE.qsize()
                cache_gift = []
                for i in range(qlength):
                    cache_gift.append(self.GIFT_QUEUE.get())
            # print(cache_gift)
            # cache_gift是所有没处理的送礼物的信息
            # 现在将他们合并为一个list
            for gift_info in cache_gift:
                if gift_info.get('room') != roomid:
                    print('error room id')
                    exit(0)
                username, gift_name, gift_num, t = gift_info.get('username'), gift_info.get(
                    'gift_name'), gift_info.get('gift_num'), gift_info.get('t')
                if username not in wait_to_send_danmu:
                    wait_to_send_danmu[username] = {}    # 新建username
                if gift_name not in wait_to_send_danmu.get(username):
                    wait_to_send_danmu[username].update(
                        {gift_name: {'gift_num': gift_num, 't': t}})   # username->gift_name
                else:
                    # 查找已经送了的有多少
                    already_num = wait_to_send_danmu[username].get(
                        gift_name, {}).get('gift_num', 0)  # 已经送了的
                    wait_to_send_danmu[username][gift_name].update(
                        {'gift_num': gift_num + already_num, 't': t})  # 更新数量

            # print(wait_to_send_danmu)

            # 检查时间是否达到推出标准
            # 这里可以重写感谢弹幕
            for username, gifts in wait_to_send_danmu.items():
                for gift_name, info in gifts.items():
                    gift_num = info.get('gift_num')
                    if gift_num == 0:
                        continue
                    if time.time() - info.get('t') > self.user.gift_comb_delay:
                        if self.is_live or (not self.user.only_live_thx):
                            await self.send_danmu(self.user.gift_thx_format.format(username=username,
                                                                                   num=gift_num,
                                                                                   giftname=gift_name,
                                                                                   random1=random.choice(
                                                                                       self.user.random_list_1),
                                                                                   random2=random.choice(
                                                                                       self.user.random_list_2),
                                                                                   random3=random.choice(self.user.random_list_3)))
                        wait_to_send_danmu[username][gift_name].update({'gift_num': 0})

            await asyncio.sleep(1)

    async def send_danmu(self, text, default_length=30):
        default_length = self.user.danmu_length
        msg = text[0:default_length]
        json_rsp = await self.user.req_s(UtilsReq.send_danmu, self.user, msg, self._room_id)
        print(json_rsp)
        if json_rsp.get('msg', '') == 'msg in 1s':  # msg repeat 不处理了
            await asyncio.sleep(0.5)
            return await self.send_danmu(text, default_length)
        if len(text) > default_length:
            await asyncio.sleep(1)
            await self.send_danmu(text[default_length:], default_length)

    async def handle_danmu(self, data: dict):
        cmd = data['cmd']
        # print(data)
        try:
            if cmd == 'DANMU_MSG':
                flag = data['info'][0][9]
                if flag == 0:
                    print(
                        f"{data['info'][2][1]}({data['info'][2][0]})在{self._room_id}: {data['info'][1]}")
            elif cmd == 'SEND_GIFT':
                room_id = self._room_id
                user_id = data['data']['uid']
                username = data['data']['uname']

                gift_name = data['data']['giftName']
                gift_num = data['data']['num']
                self.GIFT_QUEUE.put({
                    'room': room_id,
                    'username': username,
                    'uid': user_id,
                    'gift_name': gift_name,
                    'gift_num': int(gift_num),
                    't': time.time(),
                })

            elif cmd == 'GUARD_BUY':
                # user_id=data['data']['uid'],
                username = data['data']['username']
                gift_name = data['data']['gift_name']
                gift_num = data['data']['num']
                if self.is_live or (not self.user.only_live_thx):
                    await self.send_danmu(self.user.gift_thx_format.format(username=username, num=gift_num, giftname=gift_name))

            elif cmd in ['WELCOME_GUARD', 'WELCOME', 'NOTICE_MSG', 'SYS_GIFT',
                         'ACTIVITY_BANNER_UPDATE_BLS', 'ENTRY_EFFECT', 'ROOM_RANK',
                         'ACTIVITY_BANNER_UPDATE_V2', 'COMBO_END', 'ROOM_REAL_TIME_MESSAGE_UPDATE',
                         'ROOM_BLOCK_MSG', 'WISH_BOTTLE', 'WEEK_STAR_CLOCK', 'ROOM_BOX_MASTER',
                         'HOUR_RANK_AWARDS', 'ROOM_SKIN_MSG', 'RAFFLE_START', 'RAFFLE_END',
                         'GUARD_LOTTERY_START', 'GUARD_LOTTERY_END', 'GUARD_MSG',
                         'USER_TOAST_MSG', 'SYS_MSG', 'COMBO_SEND', 'ROOM_BOX_USER',
                         'TV_START', 'TV_END', 'ANCHOR_LOT_END', 'ANCHOR_LOT_AWARD',
                         'ANCHOR_LOT_CHECKSTATUS', 'ANCHOR_LOT_STAR', 'ROOM_CHANGE',
                         'new_anchor_reward', 'room_admin_entrance', 'ROOM_ADMINS']:
                pass
            elif cmd in ['LIVE']:
                print(f'开播 {self._room_id}')
                self.is_live = True
            elif cmd in ['PREPARING']:
                print(f'下播 {self._room_id}')
                self.is_live = False
            elif cmd.startswith('PK_'):
                pass
            else:
                print(data)
        except:
            traceback.print_exc()
            print(data)
        return True


# {"code":0,"msg":"","message":"","data":{"id":4099580,"uname":"bishi","block_end_time":"2020-01-03 17:36:18"}}
# {'code': -400, 'msg': '此用户已经被禁言了', 'message': '此用户已经被禁言了', 'data': []}
